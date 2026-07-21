"""Provider bridge — resolves provider:model-id strings to LangChain chat models.

Implements the three-layer provider strategy from SPEC.md §10:

1. First-party LangChain packages (18 bundled) — direct API access, lowest latency
2. OpenRouter (single package, 200+ models) — covers all gaps
3. LiteLLM Gateway (optional, self-hosted) — enterprise controls

All model imports are lazy — no provider packages are imported at module load time.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel

from pyharness.config.schema import PyHarnessConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider registry — maps provider IDs to their LangChain chat model classes.
# Format: "provider-name" → "module.path.ClassName"
#
# Every entry in this registry corresponds to an optional dependency.
# The actual import happens lazily inside resolve_model().
# ---------------------------------------------------------------------------

PROVIDER_REGISTRY: dict[str, str] = {
    "openai": "langchain_openai.ChatOpenAI",
    "anthropic": "langchain_anthropic.ChatAnthropic",
    "google-genai": "langchain_google_genai.ChatGoogleGenerativeAI",
    "google-vertexai": "langchain_google_vertexai.ChatVertexAI",
    "mistralai": "langchain_mistralai.ChatMistralAI",
    "groq": "langchain_groq.ChatGroq",
    "aws": "langchain_aws.ChatBedrock",
    "fireworks": "langchain_fireworks.ChatFireworks",
    "huggingface": "langchain_huggingface.ChatHuggingFace",
    "ollama": "langchain_ollama.ChatOllama",
    "deepseek": "langchain_deepseek.ChatDeepSeek",
    "xai": "langchain_xai.ChatXAI",
    "together": "langchain_together.ChatTogether",
    "perplexity": "langchain_perplexity.ChatPerplexity",
    "cerebras": "langchain_cerebras.ChatCerebras",
    "nvidia": "langchain_nvidia_ai_endpoints.ChatNVIDIA",
    "ibm": "langchain_ibm.ChatWatsonx",
    "cohere": "langchain_cohere.ChatCohere",
    "openrouter": "langchain_openrouter.ChatOpenRouter",
    "litellm": "langchain_litellm.ChatLiteLLMRouter",
}

# Provider names for which having no config entry is acceptable
# (because they may not need API keys at the provider level).
_NO_CONFIG_REQUIRED: frozenset[str] = frozenset({"ollama"})

# ---------------------------------------------------------------------------
# Provider model-list endpoints — live model discovery (SPEC §10)
# ---------------------------------------------------------------------------

_PROVIDER_MODEL_ENDPOINTS: dict[str, dict] = {
    "openai":        {"url": "https://api.openai.com/v1/models",           "auth": "bearer"},
    "anthropic":     {"url": "https://api.anthropic.com/v1/models",        "auth": "x-api-key"},
    "deepseek":      {"url": "https://api.deepseek.com/v1/models",           "auth": "bearer"},
    "google-genai":  {"url": "https://generativelanguage.googleapis.com/v1beta/models", "auth": "goog"},
    "groq":          {"url": "https://api.groq.com/openai/v1/models",      "auth": "bearer"},
    "mistralai":     {"url": "https://api.mistral.ai/v1/models",           "auth": "bearer"},
    "together":      {"url": "https://api.together.ai/v1/models",          "auth": "bearer"},
    "xai":           {"url": "https://api.x.ai/v1/models",                 "auth": "bearer"},
    "perplexity":    {"url": "https://api.perplexity.ai/v1/models",        "auth": "none"},
    "openrouter":    {"url": "https://openrouter.ai/api/v1/models",        "auth": "none"},
    "ollama":        {"url": "http://localhost:11434/api/tags",            "auth": "none"},
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_model(model_id: str, config: PyHarnessConfig) -> BaseChatModel:
    """Resolve a ``provider:model-id`` string to a LangChain chat model.

    Args:
        model_id: String like ``"anthropic:claude-sonnet-4-5"`` or
            ``"openrouter:openai/gpt-5"``.
        config: Full pyharness config with provider credentials.

    Returns:
        A configured :class:`BaseChatModel` ready for use in a LangGraph agent.

    Raises:
        ValueError: If the provider is unrecognised or does not have a
            matching configuration entry in ``config.provider``.

    **Resolution order** (SPEC §10.6):

    1. First-party LangChain package → native ``ChatModel`` (lowest latency)
    2. ``openrouter:`` prefix → :class:`ChatOpenRouter`
       (200+ models, single API key)
    3. ``litellm:`` prefix → :class:`ChatLiteLLMRouter`
       (enterprise gateway, requires self-hosted proxy)
    4. ``ollama:`` prefix → :class:`ChatOllama`
       (local models, no API key required)
    """
    if ":" not in model_id:
        raise ValueError(
            f"Invalid model ID {model_id!r}. "
            f"Expected format: 'provider:model-id' "
            f"(e.g. 'anthropic:claude-sonnet-4-5')"
        )

    provider_name, model_name = model_id.split(":", 1)

    # Validate the provider exists in our registry
    import_path = PROVIDER_REGISTRY.get(provider_name)
    if import_path is None:
        available = ", ".join(sorted(PROVIDER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown provider {provider_name!r}. "
            f"Available providers: {available}"
        )

    # Resolve provider configuration (may be absent for no-config providers)
    provider_config = config.provider.get(provider_name)

    if provider_config is None and provider_name not in _NO_CONFIG_REQUIRED:
        raise ValueError(
            f"Provider {provider_name!r} is not configured. "
            f"Add a '{provider_name}' entry to the 'provider' section "
            f"of your pyharness.json."
        )

    # Build constructor kwargs from the model string and provider config
    kwargs: dict[str, Any] = {"model": model_name}

    if provider_config is not None:
        if provider_config.apiKey:
            kwargs["api_key"] = provider_config.apiKey
        if provider_config.baseUrl:
            kwargs["base_url"] = provider_config.baseUrl

    logger.info(
        "resolving model %r with provider %r", model_id, provider_name
    )

    # Lazily import and instantiate the chat model class
    module_path, class_name = import_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        pkg_name = module_path.split(".")[0]
        raise ValueError(
            f"Provider {provider_name!r} requires '{pkg_name}' "
            f"which is not installed. "
            f"Install it with: pip install {pkg_name}  or  uv add {pkg_name}"
        ) from None
    model_class = getattr(module, class_name)

    return model_class(**kwargs)


def list_available_providers() -> list[str]:
    """Return the sorted list of all provider IDs that can be resolved."""
    return sorted(PROVIDER_REGISTRY.keys())


def list_available_models(config: PyHarnessConfig | None = None) -> list[str]:
    """List available models from configured providers.

    .. note::

        This is a synchronous convenience function that returns ``[]`` when no
        models are cached.  To discover models from live provider APIs, use
        :func:`fetch_models` which queries each provider's model-listing
        endpoint asynchronously.

    Args:
        config: Optional config. If provided with ``config.provider`` keys,
            returns the provider names with an empty model suffix.

    Returns:
        Sorted list of ``provider:`` prefix strings for configured providers.
    """
    if config is None or not config.provider:
        return []
    return sorted(f"{p}:" for p in config.provider)


async def _fetch_provider_models(
    provider: str,
    api_key: str,
    base_url: str | None = None,
) -> list[str]:
    """Query a single provider's model-list endpoint. Returns list of model IDs.

    The returned model IDs are prefixed with the provider name
    (``"provider:model-id"``), ready for use in :func:`fetch_models`.

    Args:
        provider: Provider ID (e.g. ``"openai"``).
        api_key: API key for the provider (may be empty for no-auth providers).
        base_url: Optional custom base URL from provider config.
            When set, it overrides the default endpoint URL from
            :data:`_PROVIDER_MODEL_ENDPOINTS`.

    Returns:
        List of ``"provider:model-id"`` strings.  Empty on error or
        unknown provider.
    """
    endpoint = _PROVIDER_MODEL_ENDPOINTS.get(provider)

    # -- Build URL ------------------------------------------------------------
    if base_url:
        url = f"{base_url.rstrip('/')}/models"
    elif endpoint:
        url = endpoint["url"]
    else:
        return []

    # -- Resolve auth mode ----------------------------------------------------
    if endpoint:
        auth = endpoint["auth"]
    else:
        # Custom base_url providers default to bearer auth
        auth = "bearer"

    # -- Build headers --------------------------------------------------------
    headers: dict[str, str] = {}
    if auth == "bearer" and api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif auth == "x-api-key" and api_key:
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif auth == "goog" and api_key:
        headers["x-goog-api-key"] = api_key
    # "none": no auth header

    # -- Fetch ----------------------------------------------------------------
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # -- Parse response (provider-specific formats) ---------------------------
    if provider == "google-genai":
        # {"models": [{"name": "models/..."}, ...]}
        return [f"{provider}:{item['name']}" for item in data.get("models", [])]
    elif provider == "ollama":
        # {"models": [{"name": "..."}, ...]}
        return [f"{provider}:{item['name']}" for item in data.get("models", [])]
    else:
        # OpenAI-compatible: {"data": [{"id": "..."}, ...]}
        return [f"{provider}:{item['id']}" for item in data.get("data", [])]


async def fetch_models(
    config: PyHarnessConfig | None = None,
    *,
    providers: set[str] | None = None,
) -> list[str]:
    """Fetch available models from every connected provider's own API.

    Each provider listed in :data:`_PROVIDER_MODEL_ENDPOINTS` is queried
    via its model-listing endpoint.  Providers with a ``baseUrl`` in their
    config use that URL instead of the default.

    Args:
        config: PyHarness config.  If *None* or has no configured
            providers, an empty list is returned.
        providers: Optional set of provider names to filter results to.
            When provided, only models matching these provider prefixes
            are returned.

    Returns:
        A deduplicated, sorted list of ``provider:model-id`` strings.
    """
    if config is None or not config.provider:
        return []

    configured = set(config.provider.keys())
    scope_providers = (
        (configured & providers) if providers is not None else configured
    )
    if not scope_providers:
        return []

    models: list[str] = []
    for p in sorted(scope_providers):
        pconf = config.provider.get(p)
        api_key = pconf.apiKey if pconf else ""
        base_url = pconf.baseUrl if pconf else None
        try:
            provider_models = await _fetch_provider_models(p, api_key, base_url)
            models.extend(provider_models)
        except Exception:
            logger.debug(
                "fetch_models: fetch failed for %r", p, exc_info=True
            )

    # Deduplicate and sort
    return sorted(set(models))


def get_small_model(config: PyHarnessConfig) -> BaseChatModel:
    """Resolve the configured ``small_model`` for lightweight / planning tasks.

    Convenience wrapper that calls :func:`resolve_model` with the value of
    ``config.small_model``.
    """
    return resolve_model(config.small_model, config)


async def verify_connection(
    provider: str,
    api_key: str,
    config: PyHarnessConfig | None = None,
) -> bool:
    """Test whether the given API key works for the provider.

    Queries the provider's model-list endpoint via
    :func:`_fetch_provider_models`.  If at least one model is returned,
    the connection is valid.  This is simpler and more reliable than
    invoking a test chat completion.

    Args:
        provider: Provider ID (e.g. ``"openai"``).
        api_key: The API key to test.
        config: PyHarness config.  If provided, ``baseUrl`` from the
            matching provider entry is forwarded.

    Returns:
        ``True`` if the key is accepted by the provider's API,
        ``False`` otherwise.
    """
    base_url: str | None = None
    if config is not None and provider in config.provider:
        base_url = config.provider[provider].baseUrl

    try:
        models = await _fetch_provider_models(provider, api_key, base_url)
        return len(models) > 0
    except Exception:
        logger.info(
            "verify_connection failed for provider %r", provider, exc_info=True
        )
        return False
