"""Tests for the Provider Bridge (SPEC §10)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# Model Fetch tests — dynamic model fetching from provider APIs (SPEC §10)
#
# These tests verify the NEW behavior where models are fetched from live
# provider APIs (OpenRouter, Ollama) instead of being hardcoded.
# ALL tests below MUST FAIL until ``fetch_models()`` is implemented and
# ``list_available_models()`` is refactored to use a cache/fetch mechanism.
# ---------------------------------------------------------------------------


def _empty_config() -> PyHarnessConfig:
    """Build a config with no providers configured."""
    return PyHarnessConfig()


def _openrouter_config() -> PyHarnessConfig:
    """Build a config with only openrouter configured."""
    return PyHarnessConfig(
        provider={
            "openrouter": ProviderConfig(apiKey="sk-or-test"),
        }
    )


def _ollama_config() -> PyHarnessConfig:
    """Build a config with only ollama configured."""
    return PyHarnessConfig(
        provider={
            "ollama": ProviderConfig(),
        }
    )


class TestModelFetch:
    """Model list must be fetched from provider APIs, not hardcoded.

    Currently ``list_available_models()`` returns a hardcoded list of 12
    model strings.  The target behavior is:

    * ``fetch_models(config)`` — async function that queries provider APIs
    * ``list_available_models(config)`` — returns cached or fetched models
    * Fallback to static list when no provider is configured
    """

    # ------------------------------------------------------------------
    # TEST 1 — fetch_models function must exist and be callable
    # ------------------------------------------------------------------

    def test_fetch_models_function_exists(self) -> None:
        """``fetch_models`` must exist as an async callable.

        FAILS: ``fetch_models`` is not defined anywhere in provider.py.
        """
        result: bool = False
        try:
            # Attempt import — must succeed for the feature to exist
            __import__("pyharness.core.provider", fromlist=["fetch_models"])
            from pyharness.core.provider import fetch_models  # noqa: F811

            # Must be callable (either sync or async)
            assert callable(fetch_models), "fetch_models must be callable"
            # Prefer async
            import asyncio

            if asyncio.iscoroutinefunction(fetch_models):
                result = True
            elif callable(fetch_models):
                result = True
        except ImportError:
            pass

        assert result, (
            "FAILS: ``fetch_models`` does not exist in pyharness.core.provider.\n"
            "  Expected: an async function that fetches model lists from provider APIs.\n"
            "  Current: no such function — models are hardcoded in list_available_models()."
        )

    # ------------------------------------------------------------------
    # TEST 2 — list_available_models must accept config and not be hardcoded
    # ------------------------------------------------------------------

    def test_list_available_models_not_purely_static(self) -> None:
        """``list_available_models()`` must accept a config parameter.

        The current implementation returns a hardcoded list unconditionally.
        The target behavior is to accept a config and return results from
        a cache or fetch mechanism.

        FAILS: current signature ignores config; return type may be wrong.
        """
        import inspect

        from pyharness.core.provider import list_available_models

        sig = inspect.signature(list_available_models)
        params = list(sig.parameters.keys())

        # Must accept config as a parameter
        has_config = "config" in params
        assert has_config, (
            "FAILS: ``list_available_models()`` must accept a ``config`` parameter.\n"
            f"  Current signature: ({', '.join(params)})\n"
            "  Expected: (config: PyHarnessConfig | None = None) -> list[str]"
        )

        # Return type must be list[str]
        return_annotation = sig.return_annotation
        is_list_str = (
            return_annotation == list[str]
            or str(return_annotation) == "list[str]"
            or (hasattr(return_annotation, "__origin__")
                and return_annotation.__origin__ is list)
        )
        assert is_list_str, (
            "FAILS: ``list_available_models`` must return ``list[str]``.\n"
            f"  Current return type: {return_annotation}"
        )

    # ------------------------------------------------------------------
    # TEST 3 — fetch_models must query OpenRouter API
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_from_openrouter_returns_list(self) -> None:
        """``fetch_models()`` with openrouter provider must call OpenRouter API.

        Mocks httpx to return a realistic OpenRouter model list, then
        verifies the returned model IDs are correctly prefixed.

        FAILS: ``fetch_models`` doesn't exist yet; even if it did, no
        HTTP fetching logic is implemented.
        """
        # Try to import fetch_models
        try:
            from pyharness.core.provider import fetch_models
        except ImportError:
            pytest.skip("fetch_models not yet implemented")

        config = _openrouter_config()
        mock_response = {
            "data": [
                {"id": "openai/gpt-5"},
                {"id": "anthropic/claude-sonnet-4-5"},
            ]
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_get_response = MagicMock()
        mock_get_response.raise_for_status = MagicMock()
        mock_get_response.json = MagicMock(return_value=mock_response)
        mock_client.get = AsyncMock(return_value=mock_get_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await fetch_models(config)

        assert isinstance(result, list), (
            f"FAILS: fetch_models must return a list, got {type(result).__name__}"
        )
        for item in result:
            assert isinstance(item, str), (
                f"FAILS: each item must be str, got {type(item).__name__}: {item!r}"
            )

        expected = [
            "openrouter:openai/gpt-5",
            "openrouter:anthropic/claude-sonnet-4-5",
        ]
        assert result == expected, (
            f"FAILS: fetch_models returned wrong results.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}"
        )

    # ------------------------------------------------------------------
    # TEST 4 — fetch_models with empty config returns static fallback
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_empty_config_returns_empty(self) -> None:
        """``fetch_models()`` with no providers must return an empty list.

        When no provider is configured, no models should be listed. The
        static fallback is only used when live fetching fails for a
        configured provider.

        FAILS: ``fetch_models`` doesn't exist.
        """
        try:
            from pyharness.core.provider import fetch_models
        except ImportError:
            pytest.skip("fetch_models not yet implemented")

        config = _empty_config()
        result = await fetch_models(config)

        assert isinstance(result, list), (
            f"FAILS: must return a list, got {type(result).__name__}"
        )
        assert len(result) == 0, (
            f"FAILS: static fallback must have 5+ models, got {len(result)}: {result}"
        )
        for item in result:
            assert isinstance(item, str), (
                f"FAILS: each item must be str, got {type(item).__name__}: {item!r}"
            )
            assert ":" in item, (
                f"FAILS: model ID must be 'provider:model-id' format, got: {item!r}"
            )

    # ------------------------------------------------------------------
    # TEST 5 — fetch_models must query Ollama API
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_with_ollama_configured(self) -> None:
        """``fetch_models()`` with ollama provider must call Ollama API.

        Mocks httpx to return a realistic Ollama model list, then
        verifies the returned model IDs are correctly prefixed.

        FAILS: ``fetch_models`` doesn't exist.
        """
        try:
            from pyharness.core.provider import fetch_models
        except ImportError:
            pytest.skip("fetch_models not yet implemented")

        config = _ollama_config()
        mock_response = {
            "models": [
                {"name": "llama3:8b"},
                {"name": "gemma3:27b"},
            ]
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_get_response = MagicMock()
        mock_get_response.raise_for_status = MagicMock()
        mock_get_response.json = MagicMock(return_value=mock_response)
        mock_client.get = AsyncMock(return_value=mock_get_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await fetch_models(config)

        assert isinstance(result, list), (
            f"FAILS: must return a list, got {type(result).__name__}"
        )
        for item in result:
            assert isinstance(item, str), (
                f"FAILS: each item must be str, got {type(item).__name__}: {item!r}"
            )

        expected = [
            "ollama:llama3:8b",
            "ollama:gemma3:27b",
        ]
        assert result == expected, (
            f"FAILS: fetch_models returned wrong results.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}"
        )
