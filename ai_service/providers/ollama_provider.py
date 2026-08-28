"""
Ollama implementation of LLMProvider -- fully local, open-source models.

Talks to an Ollama server (default http://localhost:11434) over its /api/chat
endpoint. Requires no API key and no account: `requires_api_key` is False, so
the configuration checks treat a missing key as fine for this provider.

Why this matters for a health tool: with Ollama the prediction context never
leaves the machine. context_builder still de-identifies before anything is
sent, but with a local model there is no third party to send to at all.

Structured output uses Ollama's `format` field, which accepts a JSON Schema
object and constrains generation to it. That is the same guarantee the
Anthropic provider gets from output_config.format, so the safety property
"the model has no field in which to return a risk score" holds identically on
a small local model.

Deliberately uses urllib from the standard library rather than requests or
httpx: Ollama's API is two plain JSON POSTs, and this keeps the open-source
path free of any new dependency.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Dict, Optional

from .base import (
    LLMProvider,
    LLMRequestError,
    LLMResponseError,
)

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    name = 'ollama'

    #: Runs locally -- there is no key to configure.
    requires_api_key = False

    default_base_url = 'http://localhost:11434'

    #: Low temperature: this is an explanation task, not a creative one, and
    #: small models drift further at higher temperatures.
    temperature = 0.3

    def _post(self, path: str, body: Dict) -> Dict:
        """POST JSON to the Ollama server and return the decoded response."""
        request = urllib.request.Request(
            f'{self.base_url}{path}',
            data=json.dumps(body).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            detail = ''
            try:
                detail = exc.read().decode('utf-8', errors='replace')[:200]
            except Exception:  # noqa: BLE001 - diagnostics only
                pass
            logger.warning('Ollama HTTP %s from %s: %s', exc.code, self.base_url, detail)

            # A 404 from /api/chat means the server is up but the model has
            # not been pulled -- by far the most common setup mistake, so it
            # gets a message that says what to do about it.
            if exc.code == 404:
                raise LLMRequestError(
                    f'Ollama has no model named {self.model!r}. '
                    f'Run: ollama pull {self.model}'
                ) from exc
            raise LLMRequestError(f'Ollama returned HTTP {exc.code}.') from exc
        except urllib.error.URLError as exc:
            logger.warning('Cannot reach Ollama at %s: %s', self.base_url, exc.reason)
            raise LLMRequestError(
                f'Could not reach Ollama at {self.base_url}. Is it running? '
                f'Start it with: ollama serve'
            ) from exc
        except TimeoutError as exc:
            raise LLMRequestError(
                f'Ollama timed out after {self.timeout_seconds}s. Local models on '
                f'CPU are slow -- consider raising AI_TIMEOUT_SECONDS or using a '
                f'smaller model.'
            ) from exc
        except (ValueError, TypeError) as exc:
            raise LLMResponseError('Ollama returned a non-JSON response.') from exc

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Dict,
        request_id: Optional[str] = None,
    ) -> Dict:
        payload = self._post('/api/chat', {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            # Ollama accepts a JSON Schema here and constrains generation to
            # it, the same structural guarantee the hosted provider gives.
            'format': json_schema,
            'stream': False,
            'options': {
                'temperature': self.temperature,
                'num_predict': self.max_tokens,
            },
        })

        content = (payload.get('message') or {}).get('content')
        if not content or not str(content).strip():
            raise LLMResponseError('Ollama returned an empty response.')

        try:
            data = json.loads(content)
        except (ValueError, TypeError) as exc:
            # Schema-constrained decoding makes this unlikely, but older
            # Ollama versions ignore `format` rather than rejecting it.
            raise LLMResponseError('Ollama returned malformed JSON.') from exc

        if not isinstance(data, dict):
            raise LLMResponseError('Ollama returned JSON that was not an object.')

        return data

    def list_models(self) -> list:
        """
        Names of the models installed on this Ollama server.

        Used by the status endpoint to tell a misconfigured model apart from
        an unreachable server, which are otherwise the same failure to a user.
        """
        request = urllib.request.Request(f'{self.base_url}/api/tags', method='GET')
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except Exception as exc:  # noqa: BLE001 - diagnostics only, never fatal
            raise LLMRequestError(f'Could not reach Ollama at {self.base_url}.') from exc

        return [entry.get('name', '') for entry in payload.get('models', [])]
