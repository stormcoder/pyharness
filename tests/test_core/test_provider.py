"""Tests for the Provider Bridge (SPEC §10)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pyharness.config.schema import ProviderConfig, PyHarnessConfig
from pyharness.core.provider import (
    PROVIDER_REGISTRY,
    get_small_model,
    list_available_providers,
    resolve_model,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    *,
    model: str = "anthropic:claude-sonnet-4-5",
    small_model: str = "anthropic:claude-haiku-4-5",
    providers: dict[str, ProviderConfig] | None = None,
) -> PyHarnessConfig:
    """Build a PyHarnessConfig with the given model strings and providers."""
    if providers is None:
        providers = {
            "openai": ProviderConfig(apiKey="sk-test-openai"),
            "anthropic": ProviderConfig(apiKey="sk-ant-test"),
            "openrouter": ProviderConfig(apiKey="sk-or-test"),
        }
    return PyHarnessConfig(
        model=model,
        small_model=small_model,
        provider=providers,
    )


def _mock_import_module(target_module: str, target_class: str) -> MagicMock:
    """Build a mock module that contains a mock chat model class.

    The mock class is a MagicMock whose ``return_value`` is the instance
    that :func:`resolve_model` returns.
    """
    instance = MagicMock()
    mock_class = MagicMock(return_value=instance, spec=["__call__"])
    mock_module = MagicMock()
    setattr(mock_module, target_class, mock_class)

    def _dynamic_import(name: str) -> MagicMock:
        if name == target_module:
            return mock_module
        return MagicMock()

    return instance, mock_class, _dynamic_import


# ---------------------------------------------------------------------------
# 1. Resolve a valid first-party provider
# ---------------------------------------------------------------------------


def test_resolve_model_valid() -> None:
    """Resolving "openai:gpt-4o-mini" with a configured API key returns a
    BaseChatModel."""
    config = _make_config()

    instance, mock_cls, import_fn = _mock_import_module(
        "langchain_openai", "ChatOpenAI"
    )

    with patch("importlib.import_module", side_effect=import_fn):
        model = resolve_model("openai:gpt-4o-mini", config)

    # The mock module should have been imported
    mock_cls.assert_called_once_with(
        model="gpt-4o-mini",
        api_key="sk-test-openai",
    )
    # The returned object is what the mock class returned
    assert model is instance


# ---------------------------------------------------------------------------
# 2. Unknown provider raises ValueError
# ---------------------------------------------------------------------------


def test_resolve_model_missing_provider() -> None:
    """An unknown provider raises ValueError with a helpful message listing
    available providers."""
    config = _make_config()

    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_model("nonexistent:some-model", config)


# ---------------------------------------------------------------------------
# 3. Registered but unconfigured provider raises ValueError
# ---------------------------------------------------------------------------


def test_resolve_model_no_config() -> None:
    """A provider that is in the registry but not in the config raises
    ValueError."""
    config = _make_config(providers={})  # No providers configured at all

    with pytest.raises(ValueError, match="is not configured"):
        resolve_model("groq:llama-3-70b", config)


# ---------------------------------------------------------------------------
# 4. OpenRouter resolution
# ---------------------------------------------------------------------------


def test_resolve_model_openrouter() -> None:
    """The "openrouter:" prefix resolves through ChatOpenRouter."""
    config = _make_config()

    instance, mock_cls, import_fn = _mock_import_module(
        "langchain_openrouter", "ChatOpenRouter"
    )

    with patch("importlib.import_module", side_effect=import_fn):
        model = resolve_model("openrouter:openai/gpt-5", config)

    mock_cls.assert_called_once_with(
        model="openai/gpt-5",
        api_key="sk-or-test",
    )
    assert model is instance


# ---------------------------------------------------------------------------
# 5. Ollama does not require config
# ---------------------------------------------------------------------------


def test_resolve_model_ollama_no_config_required() -> None:
    """Ollama (local models) does not require a provider config entry."""
    config = _make_config(providers={})

    instance, mock_cls, import_fn = _mock_import_module(
        "langchain_ollama", "ChatOllama"
    )

    with patch("importlib.import_module", side_effect=import_fn):
        model = resolve_model("ollama:llama3.2", config)

    mock_cls.assert_called_once_with(model="llama3.2")
    assert model is instance


# ---------------------------------------------------------------------------
# 6. list_available_providers returns registered providers
# ---------------------------------------------------------------------------


def test_list_available_providers() -> None:
    """list_available_providers returns a non-empty sorted list including
    common providers."""
    providers = list_available_providers()

    assert len(providers) > 0
    assert providers == sorted(PROVIDER_REGISTRY.keys())

    # Spot-check a few well-known entries
    assert "openai" in providers
    assert "anthropic" in providers
    assert "openrouter" in providers
    assert "ollama" in providers


# ---------------------------------------------------------------------------
# 7. get_small_model delegates correctly
# ---------------------------------------------------------------------------


def test_get_small_model() -> None:
    """get_small_model resolves config.small_model."""
    config = _make_config(
        small_model="openrouter:meta/llama-4-maverick",
    )

    instance, mock_cls, import_fn = _mock_import_module(
        "langchain_openrouter", "ChatOpenRouter"
    )

    with patch("importlib.import_module", side_effect=import_fn):
        model = get_small_model(config)

    mock_cls.assert_called_once_with(
        model="meta/llama-4-maverick",
        api_key="sk-or-test",
    )
    assert model is instance


# ---------------------------------------------------------------------------
# 8. Invalid model ID format (no colon)
# ---------------------------------------------------------------------------


def test_resolve_model_invalid_format() -> None:
    """A model string without a colon raises ValueError."""
    config = _make_config()

    with pytest.raises(ValueError, match="Invalid model ID"):
        resolve_model("just-a-string-without-colon", config)


# ---------------------------------------------------------------------------
# 9. Provider config with baseUrl
# ---------------------------------------------------------------------------


def test_resolve_model_with_base_url() -> None:
    """When a provider config has a baseUrl, it is passed as base_url."""
    config = _make_config(
        providers={
            "google-genai": ProviderConfig(
                apiKey="test-key",
                baseUrl="https://custom-endpoint.example.com/v1",
            ),
        }
    )

    instance, mock_cls, import_fn = _mock_import_module(
        "langchain_google_genai", "ChatGoogleGenerativeAI"
    )

    with patch("importlib.import_module", side_effect=import_fn):
        model = resolve_model("google-genai:gemini-2.5-pro", config)

    mock_cls.assert_called_once_with(
        model="gemini-2.5-pro",
        api_key="test-key",
        base_url="https://custom-endpoint.example.com/v1",
    )
    assert model is instance
