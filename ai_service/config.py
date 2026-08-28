"""
Configuration for the AI explanation layer.

Reads Django settings (which are themselves populated from environment
variables in config/settings.py) into one immutable object, so the rest of
the app never touches os.environ or settings directly.

The important property here is `is_configured`: it answers "can we call a
provider right now?" without raising and without ever exposing the key. Every
caller checks it first, which is how a missing key becomes a friendly 503
rather than a traceback.
"""

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class AISettings:
    enabled: bool
    provider: str
    model: str
    max_tokens: int
    timeout_seconds: int
    api_key: str
    base_url: str = ''

    @property
    def is_configured(self) -> bool:
        """
        True when the feature is switched on and the selected provider has
        what it needs to run.

        Credential requirements are per-provider: a hosted provider needs an
        API key, while a local one such as Ollama needs none. The provider
        class declares which via `requires_api_key`, so adding a keyless
        provider does not mean editing this method.
        """
        if not self.enabled:
            return False

        # Imported lazily: providers imports this module, so a top-level
        # import here would be circular.
        from .providers import PROVIDERS

        provider_class = PROVIDERS.get(self.provider)
        if provider_class is None:
            return False

        if provider_class.requires_api_key and not self.api_key:
            return False

        return True

    def public_status(self) -> dict:
        """
        Status safe to return over the API.

        Deliberately reports only whether a key is present, never its value,
        length or prefix.
        """
        return {
            'enabled': self.enabled,
            'configured': self.is_configured,
            'provider': self.provider,
            'model': self.model,
        }


def get_ai_settings() -> AISettings:
    """
    Build an AISettings from the current Django settings.

    Read fresh on each call rather than cached at import time so that tests
    can use `override_settings`, and so a deployment can change the switch
    without a process restart.
    """
    return AISettings(
        enabled=getattr(settings, 'AI_EXPLANATIONS_ENABLED', False),
        provider=getattr(settings, 'AI_PROVIDER', 'anthropic'),
        model=getattr(settings, 'AI_MODEL', 'claude-opus-5'),
        max_tokens=getattr(settings, 'AI_MAX_TOKENS', 2000),
        timeout_seconds=getattr(settings, 'AI_TIMEOUT_SECONDS', 30),
        api_key=getattr(settings, 'ANTHROPIC_API_KEY', ''),
        base_url=getattr(settings, 'AI_BASE_URL', ''),
    )
