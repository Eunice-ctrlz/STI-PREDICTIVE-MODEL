"""
Provider abstraction for the AI explanation layer.

The contract is one method: given a system prompt, a user prompt and a JSON
Schema, return a parsed dict that conforms to that schema. Nothing
provider-specific (message blocks, tool definitions, SDK response objects)
crosses this boundary, so adding Gemini/OpenAI/a local model later means
writing one subclass and registering it -- no changes to the service, the
prompts, the API or the frontend.

Every failure mode is normalised to an LLMError subclass. Callers catch
LLMError and degrade gracefully; they never see a provider SDK exception.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class LLMError(Exception):
    """Base class for every recoverable AI-layer failure."""

    #: Message shown to end users. Deliberately non-technical and reassuring
    #: about the ML result, which is unaffected by anything raised here.
    user_message = (
        'The AI explanation service is temporarily unavailable. '
        'Your prediction result is still available.'
    )


class LLMNotConfiguredError(LLMError):
    """No API key, unknown provider, or the feature is switched off."""


class LLMRequestError(LLMError):
    """The provider was reachable but the call failed (network, auth, rate limit, 5xx)."""


class LLMResponseError(LLMError):
    """The provider replied, but not with something matching the requested schema."""


class LLMProvider(ABC):
    """Base class every concrete provider implements."""

    #: Registry key, also reported in the generated_by block of a response.
    name: str = 'base'

    #: Whether this provider needs an API key to run. False for local
    #: providers such as Ollama, which talk to a process on this machine.
    #: Consulted by AISettings.is_configured and by get_provider().
    requires_api_key: bool = True

    #: Default endpoint for providers that talk to a host. Ignored by
    #: providers whose SDK resolves its own endpoint.
    default_base_url: str = ''

    def __init__(self, model: str, api_key: str = '', max_tokens: int = 2000,
                 timeout_seconds: int = 30, base_url: str = ''):
        self.model = model
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.base_url = (base_url or self.default_base_url).rstrip('/')
        self._api_key = api_key

    @abstractmethod
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Dict,
        request_id: Optional[str] = None,
    ) -> Dict:
        """
        Generate a response constrained to `json_schema` and return it parsed.

        Implementations must raise an LLMError subclass -- never a raw SDK
        exception -- for any failure.
        """
        raise NotImplementedError
