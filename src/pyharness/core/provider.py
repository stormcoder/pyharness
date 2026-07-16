"""Provider bridge — resolves provider:model-id strings to LangChain chat models.

Implements the three-layer provider strategy from SPEC.md §10:

1. First-party LangChain packages (18 bundled) — direct API access, lowest latency
2. OpenRouter (single package, 200+ models) — covers all gaps
3. LiteLLM Gateway (optional, self-hosted) — enterprise controls

All model imports are lazy — no provider packages are imported at module load time.
"""

from __future__ import annotations

import importlib
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from pyharness.config.schema import PyHarnessConfig

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

    # Lazily import and instantiate the chat model class
    module_path, class_name = import_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    model_class = getattr(module, class_name)

    return model_class(**kwargs)


def list_available_providers() -> list[str]:
    """Return the sorted list of all provider IDs that can be resolved."""
    return sorted(PROVIDER_REGISTRY.keys())


def list_available_models(config: PyHarnessConfig | None = None) -> list[str]:
    """List available models from configured providers.

    Args:
        config: Optional config. If provided with ``config.provider`` keys,
            only models from configured providers are returned.

    Returns:
        Sorted list of ``provider:model-id`` strings.
    """
    models = [
        "anthropic:claude-sonnet-4-5",
        "anthropic:claude-haiku-4-5",
        "anthropic:claude-opus-4-5",
        "openai:gpt-5",
        "openai:gpt-4o-mini",
        "openrouter:openai/gpt-5",
        "openrouter:anthropic/claude-sonnet-4-5",
        "openrouter:google/gemini-3-pro",
        "openrouter:meta/llama-4-maverick",
        "ollama:llama3",
        "ollama:gemma3",
        "google-genai:gemini-2.5-pro",
    ]
    if config is not None and config.provider:
        configured = list(config.provider.keys())
        models = [m for m in models if any(m.startswith(p) for p in configured)]
    return models


def get_small_model(config: PyHarnessConfig) -> BaseChatModel:
    """Resolve the configured ``small_model`` for lightweight / planning tasks.

    Convenience wrapper that calls :func:`resolve_model` with the value of
    ``config.small_model``.
    """
    return resolve_model(config.small_model, config)
