"""
Tests for the AI explanation layer.

Every test that would otherwise reach a network is mocked at the provider
boundary, so the suite runs offline and without an API key.

The most important test in this file is
MLIndependenceTests.test_prediction_succeeds_when_provider_always_fails: it
asserts the core architectural guarantee that the LLM can never become a
dependency of the ML prediction path.
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings

from patients.models import Patient
from prediction_engine.models import RiskPrediction

from .config import get_ai_settings
from .context_builder import build_explanation_context
from .explanation_service import validate_explanation_payload
from .models import PredictionExplanation
from .prompts import DISCLAIMER_TEXT, build_user_prompt
from .providers import (
    LLMNotConfiguredError,
    LLMRequestError,
    LLMResponseError,
    get_provider,
)
from .providers.ollama_provider import OllamaProvider
from .retrieval import NullRetriever, build_retrieval_query
from .safety import build_correction_note, screen_explanation
from .schemas import EXPLANATION_JSON_SCHEMA

EXPLAIN_URL = '/api/ai/explain-prediction'

#: A well-formed provider response, matching EXPLANATION_JSON_SCHEMA.
VALID_LLM_PAYLOAD = {
    'summary': 'The screening tool estimated a moderate chance of an STI being present.',
    'what_this_means': 'This is a statistical estimate, not a diagnosis. Only a test can confirm.',
    'important_considerations': [
        'The estimate is based on patterns across many people, not a test result.',
        'A low estimate does not rule an infection out.',
    ],
    'recommended_next_steps': [
        'Speak with a healthcare provider about testing.',
        'Ask about routine screening options.',
    ],
}

# Settings that make the AI layer look fully configured. No real key is ever
# needed because the provider itself is mocked.
AI_ON = dict(
    AI_EXPLANATIONS_ENABLED=True,
    AI_PROVIDER='anthropic',
    AI_MODEL='claude-opus-5',
    ANTHROPIC_API_KEY='test-key-not-real',
)

# The local open-source path: Ollama, deliberately with NO API key set, to
# prove a keyless provider is considered fully configured.
AI_OLLAMA = dict(
    AI_EXPLANATIONS_ENABLED=True,
    AI_PROVIDER='ollama',
    AI_MODEL='llama3.2:3b',
    ANTHROPIC_API_KEY='',
    AI_BASE_URL='http://localhost:11434',
)


class AIServiceTestCase(TestCase):
    """Shared fixtures: one patient and one stored prediction."""

    def setUp(self):
        self.client = Client()
        self.patient = Patient.objects.create(
            patient_id='TEST-001',
            first_name='Test',
            last_name='Patient',
            date_of_birth=date(1995, 6, 15),
            gender='F',
            county='Nairobi',
            phone='0700000000',
            email='test@example.com',
            marital_status='single',
            number_of_partners_12m=2,
            number_of_partners_lifetime=5,
            condom_use_frequency=0.4,
            prior_sti_history=True,
            symptoms_present=False,
        )
        self.prediction = RiskPrediction.objects.create(
            patient=self.patient,
            sti_type='general',
            risk_score=0.42,
            risk_level='moderate',
            confidence_interval_lower=0.32,
            confidence_interval_upper=0.52,
            top_risk_factors={'prior_sti_history': 0.31, 'condom_use_freq': 0.22},
            model_version='sti_risk_v1',
            model_name='random_forest',
            recommended_tests=['HIV', 'Syphilis'],
            recommended_actions='Routine screening recommended.',
            likely_stis=['Chlamydia'],
        )

    def _post_explain(self, **body):
        payload = {'prediction_id': self.prediction.id}
        payload.update(body)
        return self.client.post(
            EXPLAIN_URL, data=json.dumps(payload), content_type='application/json'
        )

    @staticmethod
    def _mock_provider(payload=None, side_effect=None):
        """A stand-in provider with the same surface as a real one."""
        provider = MagicMock()
        provider.name = 'anthropic'
        provider.model = 'claude-opus-5'
        if side_effect is not None:
            provider.generate_json.side_effect = side_effect
        else:
            provider.generate_json.return_value = payload or dict(VALID_LLM_PAYLOAD)
        return provider


@override_settings(**AI_ON)
class ExplainPredictionEndpointTests(AIServiceTestCase):
    """Valid requests, and the shape of a successful response."""

    @patch('ai_service.explanation_service.get_provider')
    def test_valid_request_returns_structured_explanation(self, mock_get_provider):
        mock_get_provider.return_value = self._mock_provider()

        response = self._post_explain()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['available'])
        self.assertEqual(body['prediction_id'], self.prediction.id)
        for field in (
            'summary', 'what_this_means', 'important_considerations',
            'recommended_next_steps', 'disclaimer', 'generated_by',
        ):
            self.assertIn(field, body)
        self.assertEqual(body['generated_by']['provider'], 'anthropic')
        self.assertEqual(body['generated_by']['model'], 'claude-opus-5')
        self.assertFalse(body['cached'])

    @patch('ai_service.explanation_service.get_provider')
    def test_explanation_is_persisted(self, mock_get_provider):
        mock_get_provider.return_value = self._mock_provider()

        self._post_explain()

        stored = PredictionExplanation.objects.get(prediction=self.prediction)
        self.assertEqual(stored.summary, VALID_LLM_PAYLOAD['summary'])
        self.assertEqual(stored.provider, 'anthropic')

    @patch('ai_service.explanation_service.get_provider')
    def test_second_request_is_served_from_cache(self, mock_get_provider):
        provider = self._mock_provider()
        mock_get_provider.return_value = provider

        self._post_explain()
        response = self._post_explain()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['cached'])
        # The provider must not be called again for an unchanged prediction.
        self.assertEqual(provider.generate_json.call_count, 1)

    @patch('ai_service.explanation_service.get_provider')
    def test_refresh_regenerates(self, mock_get_provider):
        provider = self._mock_provider()
        mock_get_provider.return_value = provider

        self._post_explain()
        response = self._post_explain(refresh=True)

        self.assertFalse(response.json()['cached'])
        self.assertEqual(provider.generate_json.call_count, 2)
        # Regeneration updates in place rather than accumulating rows.
        self.assertEqual(PredictionExplanation.objects.count(), 1)

    @patch('ai_service.explanation_service.get_provider')
    def test_disclaimer_is_server_controlled(self, mock_get_provider):
        """
        The model does not author the disclaimer.

        Even when it returns its own wording, the response carries the
        canonical constant.
        """
        rogue = dict(VALID_LLM_PAYLOAD, disclaimer='You are definitely fine!')
        mock_get_provider.return_value = self._mock_provider(payload=rogue)

        response = self._post_explain()

        self.assertEqual(response.json()['disclaimer'], DISCLAIMER_TEXT)

    @patch('ai_service.explanation_service.get_provider')
    def test_model_cannot_inject_a_risk_score(self, mock_get_provider):
        """Extra fields from the provider are dropped, not echoed to the client."""
        rogue = dict(VALID_LLM_PAYLOAD, risk_score=0.99, diagnosis='chlamydia')
        mock_get_provider.return_value = self._mock_provider(payload=rogue)

        body = self._post_explain().json()

        self.assertNotIn('risk_score', body)
        self.assertNotIn('diagnosis', body)


@override_settings(**AI_ON)
class InvalidRequestTests(AIServiceTestCase):
    """Client errors stay client errors and are not disguised as outages."""

    def test_missing_prediction_id_is_rejected(self):
        response = self.client.post(
            EXPLAIN_URL, data=json.dumps({}), content_type='application/json'
        )
        self.assertEqual(response.status_code, 422)

    def test_non_integer_prediction_id_is_rejected(self):
        response = self.client.post(
            EXPLAIN_URL,
            data=json.dumps({'prediction_id': 'not-a-number'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 422)

    def test_unknown_prediction_returns_404(self):
        response = self.client.post(
            EXPLAIN_URL,
            data=json.dumps({'prediction_id': 999999}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)


class GracefulDegradationTests(AIServiceTestCase):
    """Every AI-layer failure becomes a friendly 503, never a 500."""

    FRIENDLY = 'The AI explanation service is temporarily unavailable.'

    @override_settings(**dict(AI_ON, ANTHROPIC_API_KEY=''))
    def test_missing_api_key_returns_unavailable(self):
        response = self._post_explain()

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertFalse(body['available'])
        self.assertIn(self.FRIENDLY, body['message'])
        self.assertEqual(body['reason'], 'not_configured')
        self.assertEqual(PredictionExplanation.objects.count(), 0)

    @override_settings(**dict(AI_ON, AI_EXPLANATIONS_ENABLED=False))
    def test_disabled_feature_returns_unavailable(self):
        response = self._post_explain()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['reason'], 'not_configured')

    @override_settings(**dict(AI_ON, AI_PROVIDER='not-a-real-provider'))
    def test_unknown_provider_returns_unavailable(self):
        response = self._post_explain()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['reason'], 'not_configured')

    @override_settings(**AI_ON)
    @patch('ai_service.explanation_service.get_provider')
    def test_provider_api_failure_returns_unavailable(self, mock_get_provider):
        mock_get_provider.return_value = self._mock_provider(
            side_effect=LLMRequestError('boom')
        )

        response = self._post_explain()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['reason'], 'provider_error')
        self.assertEqual(PredictionExplanation.objects.count(), 0)

    @override_settings(**AI_ON)
    @patch('ai_service.explanation_service.get_provider')
    def test_malformed_response_returns_unavailable(self, mock_get_provider):
        """A response missing required fields must not be stored or shown."""
        mock_get_provider.return_value = self._mock_provider(
            payload={'summary': 'Only this field.'}
        )

        response = self._post_explain()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['reason'], 'provider_error')
        self.assertEqual(PredictionExplanation.objects.count(), 0)

    @override_settings(**AI_ON)
    @patch('ai_service.explanation_service.get_provider')
    def test_non_dict_response_returns_unavailable(self, mock_get_provider):
        mock_get_provider.return_value = self._mock_provider(payload=['not', 'a', 'dict'])

        self.assertEqual(self._post_explain().status_code, 503)


class SchemaValidationTests(TestCase):
    """Unit tests for validate_explanation_payload."""

    def test_valid_payload_passes(self):
        result = validate_explanation_payload(dict(VALID_LLM_PAYLOAD))
        self.assertEqual(result['summary'], VALID_LLM_PAYLOAD['summary'])
        self.assertEqual(len(result['important_considerations']), 2)

    def test_missing_field_raises(self):
        payload = dict(VALID_LLM_PAYLOAD)
        del payload['what_this_means']
        with self.assertRaises(LLMResponseError):
            validate_explanation_payload(payload)

    def test_blank_text_field_raises(self):
        with self.assertRaises(LLMResponseError):
            validate_explanation_payload(dict(VALID_LLM_PAYLOAD, summary='   '))

    def test_list_field_of_wrong_type_raises(self):
        with self.assertRaises(LLMResponseError):
            validate_explanation_payload(
                dict(VALID_LLM_PAYLOAD, recommended_next_steps='not a list')
            )

    def test_empty_list_field_raises(self):
        with self.assertRaises(LLMResponseError):
            validate_explanation_payload(
                dict(VALID_LLM_PAYLOAD, important_considerations=['', '  '])
            )

    def test_provider_schema_has_no_prediction_fields(self):
        """
        Structural safety guarantee.

        The model is given no field in which to return a score, probability,
        risk level or diagnosis, so it cannot override the ML prediction even
        if it ignores the system prompt.
        """
        properties = EXPLANATION_JSON_SCHEMA['properties']
        for forbidden in (
            'risk_score', 'probability', 'risk_level', 'diagnosis', 'confidence',
        ):
            self.assertNotIn(forbidden, properties)
        self.assertFalse(EXPLANATION_JSON_SCHEMA['additionalProperties'])


class ContextBuilderTests(AIServiceTestCase):
    """The de-identification boundary."""

    def test_context_contains_no_identifiers(self):
        context = build_explanation_context(self.prediction)
        serialised = json.dumps(context).lower()

        for identifier in (
            'test-001', 'test patient', '0700000000',
            'test@example.com', '1995', 'nairobi',
        ):
            self.assertNotIn(identifier.lower(), serialised)

    def test_age_is_sent_as_a_band_only(self):
        context = build_explanation_context(self.prediction)
        self.assertIn('age_band', context)
        self.assertNotIn('age', context)
        self.assertNotIn('date_of_birth', context)

    def test_factors_are_humanised_and_ranked(self):
        context = build_explanation_context(self.prediction)
        # prior_sti_history (0.31) outranks condom_use_freq (0.22).
        self.assertEqual(context['top_factors'][0], 'a previous STI')

    def test_textual_factor_values_are_handled(self):
        """The heuristic and fallback paths can store strings, not numbers."""
        self.prediction.top_risk_factors = {'symptoms_present': 'reported'}
        self.prediction.save()

        context = build_explanation_context(self.prediction)

        self.assertEqual(len(context['top_factors']), 1)

    def test_prompt_carries_the_score_but_forbids_recomputing_it(self):
        context = build_explanation_context(self.prediction)
        prompt = build_user_prompt(context)

        self.assertIn('42.0%', prompt)
        self.assertIn('do not recompute', prompt.lower())


class RetrievalSeamTests(AIServiceTestCase):
    """Phase 2 seam is wired but inert."""

    def test_null_retriever_returns_nothing(self):
        self.assertEqual(NullRetriever().retrieve('anything'), [])

    def test_retrieval_query_is_built_from_context(self):
        query = build_retrieval_query(build_explanation_context(self.prediction))
        self.assertIn('general STI', query)
        self.assertIn('Chlamydia', query)

    def test_documents_are_rendered_into_the_prompt_when_present(self):
        """Proves the seam works before a vector store exists behind it."""
        context = build_explanation_context(self.prediction)
        prompt = build_user_prompt(
            context,
            context_documents=[{'source': 'WHO fact sheet', 'text': 'Example guidance.'}],
        )

        self.assertIn('WHO fact sheet', prompt)
        self.assertIn('Example guidance.', prompt)


class ProviderRegistryTests(TestCase):
    """Provider selection and its failure modes."""

    @override_settings(**AI_ON)
    def test_returns_configured_provider(self):
        provider = get_provider()
        self.assertEqual(provider.name, 'anthropic')
        self.assertEqual(provider.model, 'claude-opus-5')

    @override_settings(**dict(AI_ON, ANTHROPIC_API_KEY=''))
    def test_missing_key_raises_not_configured(self):
        with self.assertRaises(LLMNotConfiguredError):
            get_provider()

    @override_settings(**dict(AI_ON, AI_PROVIDER='gemini'))
    def test_unregistered_provider_raises_not_configured(self):
        with self.assertRaises(LLMNotConfiguredError):
            get_provider()

    @override_settings(**dict(AI_ON, AI_EXPLANATIONS_ENABLED=False))
    def test_disabled_raises_not_configured(self):
        with self.assertRaises(LLMNotConfiguredError):
            get_provider()


class StatusEndpointTests(TestCase):
    """GET /api/ai/status must never leak credentials."""

    @override_settings(**AI_ON)
    def test_status_reports_configured_without_exposing_the_key(self):
        response = self.client.get('/api/ai/status')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['configured'])
        self.assertEqual(body['provider'], 'anthropic')
        self.assertNotIn('test-key-not-real', response.content.decode())
        self.assertNotIn('api_key', body)

    @override_settings(**dict(AI_ON, ANTHROPIC_API_KEY=''))
    def test_status_reports_unconfigured_when_key_is_absent(self):
        body = self.client.get('/api/ai/status').json()
        self.assertTrue(body['enabled'])
        self.assertFalse(body['configured'])

    @override_settings(**AI_ON)
    def test_public_status_never_includes_the_key(self):
        status = get_ai_settings().public_status()
        self.assertNotIn('api_key', status)
        self.assertNotIn('test-key-not-real', json.dumps(status))


class StoredExplanationEndpointTests(AIServiceTestCase):
    """GET /api/ai/explanation/{id} never calls a provider."""

    @override_settings(**AI_ON)
    @patch('ai_service.explanation_service.get_provider')
    def test_returns_stored_explanation(self, mock_get_provider):
        mock_get_provider.return_value = self._mock_provider()
        self._post_explain()
        mock_get_provider.reset_mock()

        response = self.client.get(f'/api/ai/explanation/{self.prediction.id}')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['cached'])
        mock_get_provider.assert_not_called()

    def test_missing_explanation_returns_unavailable(self):
        response = self.client.get(f'/api/ai/explanation/{self.prediction.id}')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['reason'], 'not_generated')

    def test_unknown_prediction_returns_404(self):
        self.assertEqual(
            self.client.get('/api/ai/explanation/999999').status_code, 404
        )


class MLIndependenceTests(AIServiceTestCase):
    """
    The central architectural guarantee.

    The ML prediction path must work regardless of the state of the AI layer.
    These tests fail loudly if anyone ever wires the LLM into prediction.
    """

    def _predict(self):
        return self.client.post(
            '/api/predictions/predict',
            data=json.dumps({'patient_id': self.patient.patient_id, 'sti_type': 'general'}),
            content_type='application/json',
        )

    @override_settings(**dict(AI_ON, AI_EXPLANATIONS_ENABLED=False))
    def test_prediction_succeeds_with_ai_disabled(self):
        response = self._predict()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn('risk_score', body)
        self.assertIn('risk_level', body)

    @override_settings(**dict(AI_ON, ANTHROPIC_API_KEY=''))
    def test_prediction_succeeds_with_no_api_key(self):
        self.assertEqual(self._predict().status_code, 200)

    @override_settings(**AI_ON)
    @patch('ai_service.explanation_service.get_provider')
    def test_prediction_succeeds_when_provider_always_fails(self, mock_get_provider):
        """
        With the provider hard-down, prediction is unaffected and the
        explanation degrades on its own.
        """
        mock_get_provider.side_effect = LLMRequestError('provider is down')

        prediction_response = self._predict()
        self.assertEqual(prediction_response.status_code, 200)
        self.assertIn('risk_score', prediction_response.json())

        # And the AI endpoint degrades rather than taking anything else down.
        self.assertEqual(self._post_explain().status_code, 503)

    def test_prediction_engine_does_not_import_ai_service(self):
        """
        Enforces the dependency direction: ai_service -> prediction_engine,
        never the reverse. A reverse import would let an AI failure break
        prediction at import time.
        """
        import pathlib

        engine = pathlib.Path(__file__).resolve().parent.parent / 'prediction_engine'
        for source in engine.rglob('*.py'):
            text = source.read_text(encoding='utf-8', errors='ignore')
            self.assertNotIn(
                'ai_service', text,
                f'{source.name} references ai_service; the ML engine must not '
                f'depend on the AI layer.',
            )


class OllamaProviderTests(TestCase):
    """
    The local, open-source provider.

    Every test mocks urllib at the transport boundary, so the suite still runs
    with no Ollama server installed or running.
    """

    def _provider(self, **kwargs):
        options = dict(
            model='llama3.2:3b', base_url='http://localhost:11434', timeout_seconds=180
        )
        options.update(kwargs)
        return OllamaProvider(**options)

    @staticmethod
    def _http_response(body):
        """A stand-in for the object urlopen() yields as a context manager."""
        response = MagicMock()
        response.read.return_value = json.dumps(body).encode('utf-8')
        response.__enter__ = lambda self: self
        response.__exit__ = lambda self, *args: False
        return response

    def test_requires_no_api_key(self):
        """The whole point of the local path."""
        self.assertFalse(OllamaProvider.requires_api_key)

    @override_settings(**AI_OLLAMA)
    def test_is_configured_without_any_api_key(self):
        """
        A keyless provider must count as configured.

        Before per-provider credential rules this returned False and the
        endpoint reported 'not_configured' even with Ollama running fine.
        """
        settings_obj = get_ai_settings()

        self.assertEqual(settings_obj.provider, 'ollama')
        self.assertEqual(settings_obj.api_key, '')
        self.assertTrue(settings_obj.is_configured)

    @override_settings(**AI_OLLAMA)
    def test_get_provider_returns_ollama_without_a_key(self):
        provider = get_provider()

        self.assertIsInstance(provider, OllamaProvider)
        self.assertEqual(provider.name, 'ollama')
        self.assertEqual(provider.model, 'llama3.2:3b')
        self.assertEqual(provider.base_url, 'http://localhost:11434')

    def test_default_base_url_is_used_when_unset(self):
        self.assertEqual(self._provider(base_url='').base_url, 'http://localhost:11434')

    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_successful_generation(self, mock_urlopen):
        mock_urlopen.return_value = self._http_response({
            'message': {'role': 'assistant', 'content': json.dumps(VALID_LLM_PAYLOAD)},
            'done': True,
        })

        result = self._provider().generate_json('system', 'user', EXPLANATION_JSON_SCHEMA)

        self.assertEqual(result, VALID_LLM_PAYLOAD)

    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_request_sends_the_schema_as_the_format_field(self, mock_urlopen):
        """
        The structural safety guarantee must survive the switch to a local
        model: Ollama constrains generation to the schema via `format`.
        """
        mock_urlopen.return_value = self._http_response({
            'message': {'content': json.dumps(VALID_LLM_PAYLOAD)},
        })

        self._provider().generate_json('sys', 'usr', EXPLANATION_JSON_SCHEMA)

        sent = json.loads(mock_urlopen.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(sent['format'], EXPLANATION_JSON_SCHEMA)
        self.assertFalse(sent['stream'])
        self.assertEqual(sent['model'], 'llama3.2:3b')
        self.assertEqual(sent['messages'][0]['role'], 'system')
        self.assertEqual(sent['messages'][1]['content'], 'usr')

    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_server_unreachable_is_a_request_error(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

        with self.assertRaises(LLMRequestError) as ctx:
            self._provider().generate_json('s', 'u', EXPLANATION_JSON_SCHEMA)

        self.assertIn('ollama serve', str(ctx.exception))

    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_missing_model_names_the_pull_command(self, mock_urlopen):
        """A 404 means the model was never pulled -- the commonest mistake."""
        import io as _io
        import urllib.error

        mock_urlopen.side_effect = urllib.error.HTTPError(
            'http://localhost:11434/api/chat', 404, 'Not Found', {},
            _io.BytesIO(b'{"error":"model not found"}'),
        )

        with self.assertRaises(LLMRequestError) as ctx:
            self._provider().generate_json('s', 'u', EXPLANATION_JSON_SCHEMA)

        self.assertIn('ollama pull llama3.2:3b', str(ctx.exception))

    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_timeout_suggests_raising_the_limit(self, mock_urlopen):
        """Local CPU inference is slow; the error should say so."""
        mock_urlopen.side_effect = TimeoutError('timed out')

        with self.assertRaises(LLMRequestError) as ctx:
            self._provider().generate_json('s', 'u', EXPLANATION_JSON_SCHEMA)

        self.assertIn('AI_TIMEOUT_SECONDS', str(ctx.exception))

    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_malformed_json_is_a_response_error(self, mock_urlopen):
        """Older Ollama versions ignore `format` rather than rejecting it."""
        mock_urlopen.return_value = self._http_response({
            'message': {'content': 'Here is my answer, not JSON at all.'},
        })

        with self.assertRaises(LLMResponseError):
            self._provider().generate_json('s', 'u', EXPLANATION_JSON_SCHEMA)

    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_empty_content_is_a_response_error(self, mock_urlopen):
        mock_urlopen.return_value = self._http_response({'message': {'content': '   '}})

        with self.assertRaises(LLMResponseError):
            self._provider().generate_json('s', 'u', EXPLANATION_JSON_SCHEMA)

    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_list_models(self, mock_urlopen):
        mock_urlopen.return_value = self._http_response({
            'models': [{'name': 'llama3.2:3b'}, {'name': 'qwen2.5:7b'}],
        })

        self.assertEqual(self._provider().list_models(), ['llama3.2:3b', 'qwen2.5:7b'])


class OllamaEndToEndTests(AIServiceTestCase):
    """The full endpoint running on the local provider, transport mocked."""

    @staticmethod
    def _ok_response():
        response = MagicMock()
        response.read.return_value = json.dumps({
            'message': {'content': json.dumps(VALID_LLM_PAYLOAD)},
        }).encode('utf-8')
        response.__enter__ = lambda self: self
        response.__exit__ = lambda self, *args: False
        return response

    @override_settings(**AI_OLLAMA)
    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_explanation_generated_through_ollama(self, mock_urlopen):
        mock_urlopen.return_value = self._ok_response()

        response = self._post_explain()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['generated_by']['provider'], 'ollama')
        self.assertEqual(body['generated_by']['model'], 'llama3.2:3b')
        # The server still owns the disclaimer on the local path.
        self.assertEqual(body['disclaimer'], DISCLAIMER_TEXT)

    @override_settings(**AI_OLLAMA)
    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_no_identifiers_are_sent_to_the_local_model(self, mock_urlopen):
        """De-identification applies on every provider, local included."""
        mock_urlopen.return_value = self._ok_response()

        self._post_explain()

        sent = mock_urlopen.call_args[0][0].data.decode('utf-8').lower()
        for identifier in ('test-001', 'test patient', '0700000000', 'nairobi'):
            self.assertNotIn(identifier, sent)

    @override_settings(**AI_OLLAMA)
    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_ollama_down_degrades_gracefully(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError('refused')

        response = self._post_explain()

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['available'])
        self.assertEqual(PredictionExplanation.objects.count(), 0)

    @override_settings(**AI_OLLAMA)
    @patch('ai_service.providers.ollama_provider.urllib.request.urlopen')
    def test_prediction_still_works_when_ollama_is_down(self, mock_urlopen):
        """The independence guarantee holds on the local path too."""
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError('refused')

        response = self.client.post(
            '/api/predictions/predict',
            data=json.dumps({'patient_id': self.patient.patient_id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('risk_score', response.json())

    @override_settings(**AI_OLLAMA)
    def test_status_reports_configured_with_no_key(self):
        body = self.client.get('/api/ai/status').json()

        self.assertTrue(body['configured'])
        self.assertEqual(body['provider'], 'ollama')
        self.assertEqual(body['model'], 'llama3.2:3b')


class SafetyScreenTests(TestCase):
    """
    Post-generation screening.

    The cases here are not hypothetical: the diagnostic phrasing and the
    duplicated-paragraph case are both real output captured from
    qwen2.5:0.5b running against this exact prompt.
    """

    SAFE = {
        'summary': 'This screening tool estimated a higher-than-average chance an STI could be present.',
        'what_this_means': (
            'The model compares recorded answers against patterns from many people. '
            'Only a laboratory test can establish whether an infection exists.'
        ),
        'important_considerations': [
            'Only a laboratory test can confirm whether an infection is present.',
            'A lower estimate does not rule an infection out.',
        ],
        'recommended_next_steps': [
            'Speak with a healthcare provider about arranging STI testing.',
            'Ask which tests suit your situation.',
        ],
    }

    def test_clean_explanation_passes(self):
        self.assertEqual(screen_explanation(self.SAFE), [])

    def test_real_model_output_is_caught(self):
        """Verbatim output from qwen2.5:0.5b that violated safety rule 1."""
        payload = dict(
            self.SAFE,
            what_this_means=(
                'The model suggests that the person has a high risk of contracting '
                'STIs, including chlamydia, gonorrhea, and syphilis.'
            ),
        )

        violations = screen_explanation(payload)

        self.assertTrue(violations)
        self.assertEqual(violations[0]['field'], 'what_this_means')

    def test_direct_diagnosis_is_caught(self):
        payload = dict(self.SAFE, summary='You have chlamydia and should start treatment.')
        self.assertTrue(screen_explanation(payload))

    def test_claimed_certainty_is_caught(self):
        payload = dict(self.SAFE, summary='You are definitely at risk of this infection.')
        self.assertTrue(screen_explanation(payload))

    def test_discouraging_testing_is_caught(self):
        payload = dict(
            self.SAFE,
            recommended_next_steps=['There is no need for testing at this time.'],
        )
        self.assertTrue(screen_explanation(payload))

    def test_alarmist_language_is_caught(self):
        payload = dict(self.SAFE, summary='This is an extremely dangerous situation.')
        self.assertTrue(screen_explanation(payload))

    def test_naming_an_sti_to_test_for_is_allowed(self):
        """
        The screen must not be so blunt it blocks useful advice.

        Naming an infection as something to screen for is exactly what this
        tool should say; only asserting the person HAS one is a violation.
        """
        payload = dict(
            self.SAFE,
            recommended_next_steps=[
                'Ask your provider about testing for chlamydia and gonorrhoea.',
            ],
        )
        self.assertEqual(screen_explanation(payload), [])

    def test_duplicate_paragraphs_are_caught(self):
        """Small models often emit the same text for both prose fields."""
        same = 'The model assessed risk using symptoms, partners, condoms and substance use.'
        violations = screen_explanation(
            dict(self.SAFE, summary=same, what_this_means=same)
        )

        self.assertTrue(violations)
        self.assertIn('repeats the summary', violations[-1]['reason'])

    def test_distinct_paragraphs_are_not_flagged(self):
        self.assertEqual(screen_explanation(self.SAFE), [])

    def test_correction_note_names_the_offending_phrase(self):
        violations = screen_explanation(
            dict(self.SAFE, summary='You have chlamydia.')
        )
        note = build_correction_note(violations)

        self.assertIn('you have', note.lower())
        self.assertIn('summary', note)


class SafetyRetryTests(AIServiceTestCase):
    """The screen's effect on the endpoint: retry once, then degrade."""

    UNSAFE = dict(VALID_LLM_PAYLOAD, summary='You have chlamydia and are infected.')

    @override_settings(**AI_ON)
    @patch('ai_service.explanation_service.get_provider')
    def test_unsafe_output_triggers_one_retry_then_succeeds(self, mock_get_provider):
        provider = MagicMock()
        provider.name = 'anthropic'
        provider.model = 'claude-opus-5'
        # First attempt unsafe, second clean.
        provider.generate_json.side_effect = [
            dict(self.UNSAFE), dict(VALID_LLM_PAYLOAD),
        ]
        mock_get_provider.return_value = provider

        response = self._post_explain()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(provider.generate_json.call_count, 2)
        self.assertNotIn('chlamydia', response.json()['summary'].lower())

    @override_settings(**AI_ON)
    @patch('ai_service.explanation_service.get_provider')
    def test_retry_is_told_what_was_wrong(self, mock_get_provider):
        provider = MagicMock()
        provider.name = 'anthropic'
        provider.model = 'claude-opus-5'
        provider.generate_json.side_effect = [
            dict(self.UNSAFE), dict(VALID_LLM_PAYLOAD),
        ]
        mock_get_provider.return_value = provider

        self._post_explain()

        retry_prompt = provider.generate_json.call_args_list[1].kwargs['user_prompt']
        self.assertIn('BROKE THE SAFETY RULES', retry_prompt)
        self.assertIn('you have', retry_prompt.lower())

    @override_settings(**AI_ON)
    @patch('ai_service.explanation_service.get_provider')
    def test_persistently_unsafe_output_is_never_shown(self, mock_get_provider):
        """
        Two failures means no explanation at all.

        Showing unsafe text to a patient is worse than showing none, so this
        degrades to the same friendly 503 as a provider outage.
        """
        provider = MagicMock()
        provider.name = 'anthropic'
        provider.model = 'claude-opus-5'
        provider.generate_json.return_value = dict(self.UNSAFE)
        mock_get_provider.return_value = provider

        response = self._post_explain()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(provider.generate_json.call_count, 2)
        self.assertEqual(PredictionExplanation.objects.count(), 0)

    @override_settings(**AI_ON)
    @patch('ai_service.explanation_service.get_provider')
    def test_safe_output_is_not_retried(self, mock_get_provider):
        provider = self._mock_provider()
        mock_get_provider.return_value = provider

        self._post_explain()

        self.assertEqual(provider.generate_json.call_count, 1)
