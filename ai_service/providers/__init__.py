"""
Provider registry.

To add a provider: write a class extending LLMProvider in this package and
add one line to PROVIDERS. Nothing else in the project needs to change.
"""

from typing import Dict, Type

from ..config import AISettings, get_ai_settings
from .anthropic_provider import AnthropicProvider
from .ollama_provider import OllamaProvider
from .base import (
    LLMError,
    LLMNotConfiguredError,
    LLMProvider,
    LLMRequestError,
    LLMResponseError,
)

PROVIDERS: Dict[str, Type[LLMProvider]] = {
    AnthropicProvider.name: AnthropicProvider,
    OllamaProvider.name: OllamaProvider,
}

__all__ = [
    'PROVIDERS',
    'AnthropicProvider',
    'OllamaProvider',
    'get_provider',
    'LLMProvider',
    'LLMError',
    'LLMNotConfiguredError',
    'LLMRequestError',
    'LLMResponseError',
]


def get_provider(ai_settings: AISettings = None) -> LLMProvider:
    """
    Build the configured provider.

    Raises LLMNotConfiguredError -- not a KeyError or an AttributeError -- for
    every "cannot run" case, so callers have exactly one exception type to
    handle for the whole misconfiguration family.
    """
    ai_settings = ai_settings or get_ai_settings()

    if not ai_settings.enabled:
        raise LLMNotConfiguredError('The AI explanation layer is disabled.')

    provider_class = PROVIDERS.get(ai_settings.provider)
    if provider_class is None:
        known = ', '.join(sorted(PROVIDERS)) or 'none'
        raise LLMNotConfiguredError(
            f'Unknown AI provider {ai_settings.provider!r}. Registered providers: {known}.'
        )

    # Only hosted providers need credentials. A local provider such as
    # Ollama declares requires_api_key = False and runs without one.
    if provider_class.requires_api_key and not ai_settings.api_key:
        raise LLMNotConfiguredError(
            f'No API key configured for the {ai_settings.provider!r} provider.'
        )

    return provider_class(
        model=ai_settings.model,
        api_key=ai_settings.api_key,
        max_tokens=ai_settings.max_tokens,
        timeout_seconds=ai_settings.timeout_seconds,
        base_url=ai_settings.base_url,
    )
