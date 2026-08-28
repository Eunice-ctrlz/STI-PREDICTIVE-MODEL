"""
Anthropic implementation of LLMProvider.

Uses the Messages API with `output_config.format` (structured outputs), which
constrains generation to the supplied JSON Schema. That matters for safety as
much as for parsing: the schema has no field for a risk score or a diagnosis,
so the model has no channel through which to emit one. The prompt asks for
good behaviour; the schema enforces the shape.
"""

import json
import logging
from typing import Dict, Optional

from .base import (
    LLMNotConfiguredError,
    LLMProvider,
    LLMRequestError,
    LLMResponseError,
)

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    name = 'anthropic'

    def _client(self):
        # Imported lazily so that the app -- and therefore the whole Django
        # project -- still starts when the `anthropic` package is absent.
        try:
            import anthropic
        except ImportError as exc:
            raise LLMNotConfiguredError(
                'The anthropic package is not installed. Run: pip install -r requirements.txt'
            ) from exc

        if not self._api_key:
            raise LLMNotConfiguredError('ANTHROPIC_API_KEY is not set.')

        return anthropic, anthropic.Anthropic(
            api_key=self._api_key,
            timeout=float(self.timeout_seconds),
        )

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Dict,
        request_id: Optional[str] = None,
    ) -> Dict:
        anthropic, client = self._client()

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=[{'role': 'user', 'content': user_prompt}],
                output_config={
                    'format': {
                        'type': 'json_schema',
                        'schema': json_schema,
                    }
                },
            )
        except anthropic.APIStatusError as exc:
            # Log the status but never the key or the full request body.
            logger.warning(
                'Anthropic API error (status=%s) for request %s',
                getattr(exc, 'status_code', 'unknown'), request_id,
            )
            raise LLMRequestError(
                f'Provider returned an error (status {getattr(exc, "status_code", "unknown")}).'
            ) from exc
        except anthropic.APIConnectionError as exc:
            logger.warning('Anthropic connection error for request %s', request_id)
            raise LLMRequestError('Could not reach the AI provider.') from exc
        except Exception as exc:  # noqa: BLE001 - normalise anything unforeseen
            logger.exception('Unexpected AI provider failure for request %s', request_id)
            raise LLMRequestError('Unexpected AI provider failure.') from exc

        # A safety refusal is a normal 200 response, not an exception. Check it
        # before touching content.
        if getattr(response, 'stop_reason', None) == 'refusal':
            raise LLMResponseError('The AI provider declined to answer this request.')

        text = next(
            (block.text for block in response.content if getattr(block, 'type', None) == 'text'),
            None,
        )
        if not text:
            raise LLMResponseError('The AI provider returned an empty response.')

        try:
            data = json.loads(text)
        except (ValueError, TypeError) as exc:
            raise LLMResponseError('The AI provider returned malformed JSON.') from exc

        if not isinstance(data, dict):
            raise LLMResponseError('The AI provider returned JSON that was not an object.')

        return data
