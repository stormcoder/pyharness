"""Tests for the Provider Bridge (SPEC §10)."""

from __future__ import annotations

import importlib
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

        expected = sorted([
            "openrouter:openai/gpt-5",
            "openrouter:anthropic/claude-sonnet-4-5",
        ])
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

        expected = sorted([
            "ollama:llama3:8b",
            "ollama:gemma3:27b",
        ])
        assert result == expected, (
            f"FAILS: fetch_models returned wrong results.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}"
        )


# =============================================================================
# CONNECTION VERIFICATION — provider connection tests (SPEC §10)
#
# The connect flow must validate that the API key the user provides actually
# works BEFORE dismissing the ConnectScreen.  This prevents users from
# thinking they're connected when they're not.
#
# Currently ``verify_connection()`` does NOT exist anywhere in
# ``src/pyharness/core/provider.py`` — these tests will FAIL until it is
# implemented.
# =============================================================================


class TestProviderConnection:
    """Provider connection verification must exist and work correctly.

    The connect flow currently has NO connection test — ``_save_provider_key``
    writes a ``{env:...}`` placeholder and returns success immediately.
    These tests define the expected behavior and SHOULD FAIL.
    """

    # ------------------------------------------------------------------
    # TEST 1 — verify_connection function must exist
    # ------------------------------------------------------------------

    def test_verify_connection_function_exists(self) -> None:
        """``verify_connection`` must be importable from the provider module.

        FAILS: ``verify_connection`` is not defined anywhere in
        ``src/pyharness/core/provider.py``.
        """
        import asyncio

        try:
            # Attempt import — MUST succeed for the feature to exist
            __import__("pyharness.core.provider", fromlist=["verify_connection"])
            from pyharness.core.provider import verify_connection  # noqa: F811

            # Must be callable
            assert callable(verify_connection), (
                "verify_connection must be callable"
            )

            # Must accept (provider: str, api_key: str, config: PyHarnessConfig | None)
            # and return a coroutine (async).
            sig = verify_connection.__name__
            assert asyncio.iscoroutinefunction(verify_connection), (
                "FAILS: verify_connection must be an async function (coroutine).\n"
                f"  Found: {sig} is not a coroutine function."
            )
        except ImportError:
            pytest.fail(
                "FAILS: ``verify_connection`` does not exist in pyharness.core.provider.\n"
                "  Expected: async function verify_connection(provider, api_key, config=None) -> bool\n"
                "  Current: no connection test — ConnectScreen._save_provider_key() saves\n"
                "  a placeholder and returns immediately.  Users are never told whether\n"
                "  their API key actually works."
            )

    # ------------------------------------------------------------------
    # TEST 2 — verify_connection with valid key returns True
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_connection_with_valid_key_returns_true(self) -> None:
        """``verify_connection("openai", "sk-test")`` must return ``True``.

        Mocks ``_fetch_provider_models`` to return a non-empty model list,
        simulating a successful API call.
        """
        try:
            from pyharness.core.provider import verify_connection
        except ImportError:
            pytest.skip("verify_connection not yet implemented")

        config = _make_config()

        with patch(
            "pyharness.core.provider._fetch_provider_models",
            return_value=["openai:gpt-5", "openai:gpt-4o-mini"],
        ) as mock_fetch:
            result = await verify_connection("openai", "sk-test123", config)

        assert result is True, (
            f"FAILS: verify_connection with valid key must return True.\n"
            f"  Got: {result!r}\n"
            f"  Expected: True (live model list returned models)"
        )
        mock_fetch.assert_called_once_with("openai", "sk-test123", None)

    # ------------------------------------------------------------------
    # TEST 3 — verify_connection with invalid key returns False
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_connection_with_invalid_key_returns_false(self) -> None:
        """``verify_connection("openai", "bad-key")`` must return ``False``.

        Mocks ``_fetch_provider_models`` to raise ``HTTPStatusError``
        (401 Unauthorized) — simulating an auth failure.
        """
        try:
            from pyharness.core.provider import verify_connection
        except ImportError:
            pytest.skip("verify_connection not yet implemented")

        config = _make_config()

        with patch(
            "pyharness.core.provider._fetch_provider_models",
            side_effect=Exception("401 Unauthorized"),
        ):
            result = await verify_connection("openai", "bad-key", config)

        assert result is False, (
            f"FAILS: verify_connection with invalid key must return False.\n"
            f"  Got: {result!r}\n"
            f"  Expected: False (auth failure should not crash, just return False)"
        )


# =============================================================================
# DEEPSEEK PROVIDER — provider resolution and error handling
# =============================================================================
# The deepseek provider is registered in PROVIDER_REGISTRY but
# ``langchain-deepseek`` may not be installed.  These tests verify
# the resolve/connection paths handle missing modules gracefully and
# use real model IDs (not ``test-model``) for connection verification.
# ALL TESTS BELOW MUST FAIL until the issues are fixed.


class TestDeepSeekProvider:
    """DeepSeek provider resolution and connection verification.

    **Known gaps:**

    1. ``langchain-deepseek`` is an optional dependency.  When missing,
       :func:`resolve_model` raises a raw ``ModuleNotFoundError`` with
       no guidance about installing the package.
    2. :func:`verify_connection` hardcodes ``provider:test-model`` as
       the model ID — ``test-model`` is not a real model for any provider,
       so valid API keys can still fail verification.
    3. Errors in ``verify_connection`` are logged at ``DEBUG`` level
       and are invisible with the default ``INFO`` log level.
    """

    # ------------------------------------------------------------------
    # TEST 1 — deepseek provider must be in the registry
    # ------------------------------------------------------------------

    def test_deepseek_provider_in_registry(self) -> None:
        """The 'deepseek' provider must be a key in PROVIDER_REGISTRY.

        PASSES: ``deepseek`` exists in the registry pointing to
        ``langchain_deepseek.ChatDeepSeek``.

        If it were removed, this test verifies a guardrail.
        """
        assert "deepseek" in PROVIDER_REGISTRY, (
            "FAILS: 'deepseek' is not in PROVIDER_REGISTRY.\n"
            "  If this was intentional, update this test."
        )
        assert PROVIDER_REGISTRY["deepseek"] == "langchain_deepseek.ChatDeepSeek"

    # ------------------------------------------------------------------
    # TEST 2 — missing module gives a helpful install error
    # ------------------------------------------------------------------

    def test_resolve_deepseek_missing_module_gives_helpful_error(self) -> None:
        """When langchain-deepseek is not installed, the error must guide
        the user to install it.

        Mocks ``importlib.import_module`` to raise ``ModuleNotFoundError``
        for ``langchain_deepseek``.  The resulting error message must
        contain ``"install"`` or ``"pip install langchain-deepseek"``.

        FAILS: current code catches ModuleNotFoundError in the wrong
        place — ``resolve_model`` propagates the raw exception without
        any helpful guidance.
        """
        config = _make_config(
            providers={
                "deepseek": ProviderConfig(apiKey="sk-test-deepseek"),
            }
        )

        real_import = importlib.import_module

        def _failing_import(name: str):
            if name == "langchain_deepseek":
                raise ModuleNotFoundError(
                    f"No module named '{name}'"
                )
            return real_import(name)

        with patch("importlib.import_module", side_effect=_failing_import):
            try:
                resolve_model("deepseek:deepseek-chat", config)
            except ValueError as exc:
                # This is the preferred path: a ValueError with install guidance
                msg = str(exc).lower()
                assert (
                    "install" in msg or "pip install langchain-deepseek" in msg
                ), (
                    "FAILS: Error message for missing langchain-deepseek must "
                    "include install guidance like 'pip install langchain-deepseek'.\n"
                    f"  Actual error: {exc}\n"
                    "  Current: raw ModuleNotFoundError — no install hints."
                )
            except ModuleNotFoundError as exc:
                pytest.fail(
                    "FAILS: resolve_model raises raw ModuleNotFoundError for "
                    "missing langchain-deepseek.\n\n"
                    f"  Actual: {exc}\n"
                    "  Expected: ValueError with 'pip install langchain-deepseek'\n"
                    "  guidance so the user knows what to install.\n\n"
                    "  To fix: wrap ``importlib.import_module`` in a try/except\n"
                    "  and raise ValueError(f'Provider ... requires langchain-deepseek. "
                    "Install: pip install langchain-deepseek')\n"
                )
            else:
                pytest.fail(
                    "FAILS: resolve_model did not raise for missing module.\n"
                    "  The import was mocked to raise ModuleNotFoundError.\n"
                    "  Either the mock didn't work or resolve_model is swallowing "
                    "errors silently."
                )

    # ------------------------------------------------------------------
    # TEST 3 — verify_connection must use a real model ID
    # ------------------------------------------------------------------

    def test_verify_connection_uses_real_model_id(self) -> None:
        """verify_connection must use live model discovery, not a fake model ID.

        ``verify_connection`` now queries ``_fetch_provider_models`` to
        verify provider connectivity — there is no risk of a hardcoded
        ``test-model`` being used.  This test validates that the provider
        name is correctly forwarded.

        Previously: ``verify_connection`` hardcoded ``provider:test-model``
        which was rejected by provider APIs even with valid keys.
        Now: it calls ``_fetch_provider_models(provider, api_key, base_url)``
        which queries the provider's real model-list endpoint.

        Tests that ``_fetch_provider_models`` is called with the right
        provider and key.
        """
        import asyncio
        from unittest.mock import patch

        from pyharness.core.provider import verify_connection

        config = _make_config()

        with patch(
            "pyharness.core.provider._fetch_provider_models",
            return_value=["openai:gpt-4o-mini"],
        ) as mock_fetch:
            asyncio.run(verify_connection("openai", "sk-test123", config))

        mock_fetch.assert_called_once_with("openai", "sk-test123", None)


# =============================================================================
# CONNECTED PROVIDER FILTERING — fetch_models only returns connected providers
# =============================================================================
# When a providers set is passed to fetch_models(), only those providers'
# models are returned.  This prevents model leakage from unconnected providers
# (e.g. openrouter models showing up when only deepseek is connected).


class TestConnectedProviderFiltering:
    """fetch_models must filter results to only connected providers."""

    # ------------------------------------------------------------------
    # TEST 1 — connected providers filter restricts results
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_only_connected_providers(self) -> None:
        """With connected={'deepseek'} and config having deepseek+openrouter,
        only deepseek models (from static fallback) must be returned.

        The config has two providers but the filter says only deepseek
        is connected — openrouter models must NOT appear.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "deepseek": ProviderConfig(apiKey="sk-test-ds"),
                "openrouter": ProviderConfig(apiKey="sk-or-test"),
            }
        )

        result = await fetch_models(config, providers={"deepseek"})

        assert isinstance(result, list)
        # deepseek has no live fetch, so it falls back to verifier model.
        for model in result:
            assert model.startswith("deepseek:"), (
                f"FAILS: model '{model}' does not start with 'deepseek:'.\n"
                f"  All models must be from the connected provider set.\n"
                f"  Full result: {result}"
            )
            assert not model.startswith("openrouter:"), (
                f"FAILS: openrouter model '{model}' leaked into results "
                f"when only deepseek is connected."
            )

    # ------------------------------------------------------------------
    # TEST 2 — empty connected set returns empty model list
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_empty_when_no_connected_providers(self) -> None:
        """With connected=set() (empty), fetch_models must return an empty
        list regardless of what providers exist in the config."""
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "deepseek": ProviderConfig(apiKey="sk-test-ds"),
                "openrouter": ProviderConfig(apiKey="sk-or-test"),
                "ollama": ProviderConfig(),
            }
        )

        result = await fetch_models(config, providers=set())

        assert isinstance(result, list)
        assert len(result) == 0, (
            f"FAILS: empty connected set must produce empty model list.\n"
            f"  Got {len(result)} models: {result}"
        )

    # ------------------------------------------------------------------
    # TEST 3 — None providers filter (backward compat) includes all
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_no_filter_includes_all_configured(self) -> None:
        """When providers=None (default), all configured providers are
        included (backward-compatible behavior)."""
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "openrouter": ProviderConfig(apiKey="sk-or-test"),
            }
        )

        # Mock the HTTP fetch to return known data
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
            result = await fetch_models(config)  # no providers filter

        assert len(result) >= 2
        for model in result:
            assert model.startswith("openrouter:"), (
                f"Without providers filter, all configured providers "
                f"should be included. Got: {model!r}"
            )

    # ------------------------------------------------------------------
    # TEST 4 — mixed connected/unconnected providers
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_mixed_connected_and_unconnected(self) -> None:
        """With connected={'deepseek'} and config having deepseek+openrouter,
        only deepseek-prefixed models must be returned.  OpenRouter models
        must NOT leak — even though openrouter IS configured."""
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "deepseek": ProviderConfig(apiKey="sk-test-ds"),
                "openrouter": ProviderConfig(apiKey="sk-or-test"),
            }
        )

        result = await fetch_models(config, providers={"deepseek"})

        assert isinstance(result, list), (
            f"FAILS: must return list, got {type(result).__name__}"
        )

        # Every model must be deepseek-prefixed
        for model in result:
            assert model.startswith("deepseek:"), (
                f"FAILS: model '{model}' leaked from unconnected provider.\n"
                f"  Only deepseek is connected, but got {model!r}.\n"
                f"  Full result: {result}"
            )

    # ------------------------------------------------------------------
    # TEST 5 — deepseek-only connected, no other providers in config
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_deepseek_only_provider_in_config(self) -> None:
        """With connected={'deepseek'} and ONLY deepseek in the config,
        the result must be deepseek models from verifier model —
        never openrouter or other providers."""
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "deepseek": ProviderConfig(apiKey="sk-test-ds"),
            }
        )

        result = await fetch_models(config, providers={"deepseek"})

        assert isinstance(result, list)
        # All models must be deepseek-prefixed — no cross-contamination
        for model in result:
            prefix = model.split(":", 1)[0]
            assert prefix == "deepseek", (
                f"FAILS: model '{model}' has prefix '{prefix}', "
                f"expected 'deepseek'. Full result: {result}"
            )

    # ------------------------------------------------------------------
    # TEST 6 — _VERIFY_MODELS has known entries for common providers
    # ------------------------------------------------------------------

    def test_verify_models_has_entries_for_common_providers(self) -> None:
        """``_VERIFY_MODELS`` must NOT be importable — all models come from
        live provider APIs via ``_PROVIDER_MODEL_ENDPOINTS``."""
        try:
            from pyharness.core.provider import _VERIFY_MODELS  # noqa: F401

            exists = True
        except ImportError:
            exists = False

        assert not exists, (
            "FAILS: ``_VERIFY_MODELS`` is still importable from provider.py.\n"
            "  Expected: ImportError — the hardcoded model dict must be removed.\n"
            "  All model IDs come from live provider APIs via _PROVIDER_MODEL_ENDPOINTS."
        )


# =============================================================================
# REMOVE _STATIC_MODELS — all models from live APIs or _VERIFY_MODELS fallback
# =============================================================================
# ``_STATIC_MODELS`` is a hardcoded list of 12 model strings that injects
# cross-contamination between providers (e.g. openrouter models appearing
# when only deepseek is configured).  It must be removed.
#
# After removal, providers without live-model endpoints (deepseek, anthropic,
# openai, etc.) must fall back to ``_VERIFY_MODELS`` — which returns exactly
# ONE well-known model per provider, not a hardcoded buffet.
#
# ALL TESTS IN THIS CLASS MUST FAIL until ``_STATIC_MODELS`` is gone and
# ``fetch_models()`` no longer references it.
# =============================================================================


class TestNoStaticModels:
    """_STATIC_MODELS must be removed; all models from live APIs or verifier."""

    # ------------------------------------------------------------------
    # TEST 1 — _STATIC_MODELS constant must NOT be importable
    # ------------------------------------------------------------------

    def test_static_models_constant_removed(self) -> None:
        """``from pyharness.core.provider import _STATIC_MODELS`` must raise
        ``ImportError``.

        The constant should be deleted entirely — no fallback list of models.
        FAILS: ``_STATIC_MODELS`` still exists at provider.py lines 29-42.
        """
        from pyharness.core import provider as provider_mod

        exists = hasattr(provider_mod, "_STATIC_MODELS")
        assert not exists, (
            "FAILS: ``_STATIC_MODELS`` constant still exists in provider.py.\n"
            "  Expected: ImportError — the constant must be removed.\n"
            "  All models must come from live APIs (OpenRouter, Ollama)\n"
            "  or from ``_VERIFY_MODELS`` per-provider fallback.\n"
            "  No hardcoded list."
        )

    # ------------------------------------------------------------------
    # TEST 2 — fetch_models source must NOT reference _STATIC_MODELS
    # ------------------------------------------------------------------

    def test_fetch_models_does_not_reference_static_list(self) -> None:
        """The source code of ``fetch_models()`` must NOT contain
        ``_STATIC_MODELS``.

        FAILS: ``fetch_models`` references ``_STATIC_MODELS`` at lines
        237, 282, and 293 for its static fallback logic.
        """
        import inspect
        from pyharness.core.provider import fetch_models

        source = inspect.getsource(fetch_models)
        has_static_ref = "_STATIC_MODELS" in source

        assert not has_static_ref, (
            "FAILS: ``fetch_models()`` still references ``_STATIC_MODELS``.\n"
            "  Found in source — the function must NOT use any static model list.\n"
            "  Providers without live endpoints (deepseek, anthropic, etc.)\n"
            "  must use ``_VERIFY_MODELS`` to get ONE model per provider.\n\n"
            f"  Source excerpt (first 500 chars):\n{source[:500]}..."
        )

    # ------------------------------------------------------------------
    # TEST 3 — deepseek-only connected → models from live API, no cross-contamination
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_deepseek_only_returns_verifier_model(self) -> None:
        """With connected providers = {"deepseek"}, ``fetch_models()`` must
        return only models from the deepseek live API.

        No openrouter, anthropic, openai, ollama, or any other models.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "deepseek": ProviderConfig(apiKey="sk-test-ds"),
            }
        )

        with patch(
            "pyharness.core.provider._fetch_provider_models",
            return_value=["deepseek:deepseek-chat", "deepseek:deepseek-reasoner"],
        ) as mock_fetch:
            result = await fetch_models(config, providers={"deepseek"})

        assert isinstance(result, list), (
            f"FAILS: must return list, got {type(result).__name__}"
        )
        expected = sorted(["deepseek:deepseek-chat", "deepseek:deepseek-reasoner"])
        assert result == expected, (
            "FAILS: deepseek-only connected must return only deepseek models from live API.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}\n\n"
            "  Models from other providers leaked in."
        )
        mock_fetch.assert_called_once_with("deepseek", "sk-test-ds", None)

    # ------------------------------------------------------------------
    # TEST 4 — openai-only connected → models from live API
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_openai_only_returns_verifier_model(self) -> None:
        """With connected = {"openai"}, returns only models from the openai
        live API.

        No models from other providers.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "openai": ProviderConfig(apiKey="sk-test-oai"),
            }
        )

        with patch(
            "pyharness.core.provider._fetch_provider_models",
            return_value=["openai:gpt-5", "openai:gpt-4o-mini"],
        ) as mock_fetch:
            result = await fetch_models(config, providers={"openai"})

        expected = sorted(["openai:gpt-5", "openai:gpt-4o-mini"])
        assert result == expected, (
            "FAILS: openai-only connected must return only openai models from live API.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}\n\n"
            "  Models from other providers leaked in."
        )
        mock_fetch.assert_called_once_with("openai", "sk-test-oai", None)

    # ------------------------------------------------------------------
    # TEST 5 — anthropic-only connected → models from live API
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_anthropic_only_returns_verifier_model(self) -> None:
        """With connected = {"anthropic"}, returns only models from the
        anthropic live API.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "anthropic": ProviderConfig(apiKey="sk-ant-test"),
            }
        )

        with patch(
            "pyharness.core.provider._fetch_provider_models",
            return_value=[
                "anthropic:claude-sonnet-4-5",
                "anthropic:claude-opus-4-5",
                "anthropic:claude-haiku-4-5",
            ],
        ) as mock_fetch:
            result = await fetch_models(config, providers={"anthropic"})

        expected = sorted([
            "anthropic:claude-sonnet-4-5",
            "anthropic:claude-opus-4-5",
            "anthropic:claude-haiku-4-5",
        ])
        assert result == expected, (
            "FAILS: anthropic-only connected must return only anthropic models from live API.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}\n\n"
            "  Models from other providers leaked in."
        )
        mock_fetch.assert_called_once_with("anthropic", "sk-ant-test", None)

    # ------------------------------------------------------------------
    # TEST 6 — unknown provider → empty list
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_unknown_provider_returns_empty(self) -> None:
        """With connected = {"nonexistent-provider"}, returns empty list ``[]``.

        An unknown provider has no entry in ``_VERIFY_MODELS`` and no live
        endpoint — so it must return an empty list, NOT fall back to the
        static model buffet.

        FAILS: static fallback or verifier-model uses default
        ``"gpt-4o-mini"`` which creates a leaking model entry.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "nonexistent-provider": ProviderConfig(apiKey="sk-fake"),
            }
        )

        result = await fetch_models(config, providers={"nonexistent-provider"})

        assert result == [], (
            "FAILS: unknown provider must return empty list.\n"
            f"  Got: {result}\n\n"
            "  Static fallback should not be used for unknown providers.\n"
            "  The verifier-model default 'gpt-4o-mini' should NOT create\n"
            "  'nonexistent-provider:gpt-4o-mini' — that's nonsensical."
        )

    # ------------------------------------------------------------------
    # TEST 7 — mixed live providers → all from live APIs, no cross-contamination
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_mixed_live_and_non_live_no_static_leak(self) -> None:
        """With connected = {"openrouter", "deepseek"}, all models come from
        each provider's live API.

        No static models from unrelated providers (no ``anthropic:claude-sonnet-4-5``,
        no ``openai:gpt-5``, no ``ollama:llama3``, etc.).

        Mocks ``_fetch_provider_models`` so both providers return known models.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "openrouter": ProviderConfig(apiKey="sk-or-test"),
                "deepseek": ProviderConfig(apiKey="sk-test-ds"),
            }
        )

        async def _mock_fetch(provider: str, api_key: str, base_url=None):
            if provider == "openrouter":
                return [
                    "openrouter:openai/gpt-5",
                    "openrouter:anthropic/claude-sonnet-4-5",
                ]
            elif provider == "deepseek":
                return [
                    "deepseek:deepseek-chat",
                    "deepseek:deepseek-reasoner",
                ]
            return []

        with patch(
            "pyharness.core.provider._fetch_provider_models",
            side_effect=_mock_fetch,
        ):
            result = await fetch_models(config, providers={"openrouter", "deepseek"})

        assert isinstance(result, list)
        for model in result:
            prefix = model.split(":", 1)[0]
            assert prefix in ("openrouter", "deepseek"), (
                "FAILS: model from unrelated provider leaked into result.\n"
                f"  Model: {model!r}\n"
                f"  Full result: {result}\n\n"
                "  Only openrouter and deepseek models allowed.\n"
                "  No models from unrelated providers."
            )

        # deepseek must appear (from live API)
        assert "deepseek:deepseek-chat" in result, (
            f"FAILS: deepseek:deepseek-chat missing from result.\n"
            f"  Result: {result}"
        )

        # openrouter models from live API must appear
        assert "openrouter:openai/gpt-5" in result, (
            f"FAILS: openrouter:openai/gpt-5 missing from live API result.\n"
            f"  Result: {result}"
        )


# =============================================================================
# LIVE MODEL DISCOVERY — fetch_models queries each provider's own API
# =============================================================================
# The SPEC mandates that every model ID comes from a provider's own API.
# No ``_STATIC_MODELS``, no ``_VERIFY_MODELS``, no hardcoded IDs.
# ``fetch_models()`` must query each connected provider's model-listing endpoint.
#
# ALL TESTS IN THIS CLASS MUST FAIL:
#   * ``_VERIFY_MODELS`` still exists as a fallback
#   * Only openrouter/ollama use live APIs; all other providers use verifier models
#   * No custom ``baseUrl`` support for model discovery
#   * API failures fall back to verifier models instead of returning empty
# =============================================================================


class TestLiveModelDiscovery:
    """fetch_models must query each provider's own model-listing API.

    Currently only openrouter and ollama are "live"; all other providers
    (openai, deepseek, anthropic, google-genai, etc.) fall back to
    ``_VERIFY_MODELS`` hardcoded entries.
    """

    # ------------------------------------------------------------------
    # 1. OpenAI — must query /v1/models with Bearer auth
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_queries_openai_api(self) -> None:
        """With connected={"openai"}, must query https://api.openai.com/v1/models.

        Mock HTTP 200 with ``{"data": [{"id":"gpt-5"},{"id":"gpt-4o-mini"}]}``.
        Assert returns ``["openai:gpt-5", "openai:gpt-4o-mini"]``.

        FAILS: openai is NOT in the live_providers set; fetch_models falls
        back to ``_VERIFY_MODELS`` which returns ``["openai:gpt-4o-mini"]``
        instead of the full list.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "openai": ProviderConfig(apiKey="sk-test-openai"),
            }
        )

        mock_response = {
            "data": [
                {"id": "gpt-5"},
                {"id": "gpt-4o-mini"},
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
            result = await fetch_models(config, providers={"openai"})

        # Must query the OpenAI endpoint
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args[0]
        assert call_args[0] == "https://api.openai.com/v1/models", (
            "FAILS: fetch_models must query https://api.openai.com/v1/models.\n"
            f"  Actual URL: {call_args[0]}\n"
            "  Current: openai is not a live provider — uses _VERIFY_MODELS fallback."
        )

        expected = sorted(["openai:gpt-5", "openai:gpt-4o-mini"])
        assert result == expected, (
            "FAILS: fetch_models did not return live OpenAI models.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}\n"
            "  Current: returns ['openai:gpt-4o-mini'] from _VERIFY_MODELS."
        )

    # ------------------------------------------------------------------
    # 2. DeepSeek — must query /models with Bearer auth
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_queries_deepseek_api(self) -> None:
        """With connected={"deepseek"}, must query https://api.deepseek.com/models.

        Mock HTTP 200 with ``{"data": [{"id":"deepseek-chat"},{"id":"deepseek-reasoner"}]}``.
        Assert returns ``["deepseek:deepseek-chat", "deepseek:deepseek-reasoner"]``.

        FAILS: deepseek is NOT in the live_providers set; falls back to
        ``_VERIFY_MODELS`` returning ``["deepseek:deepseek-chat"]`` only.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "deepseek": ProviderConfig(apiKey="sk-test-ds"),
            }
        )

        mock_response = {
            "data": [
                {"id": "deepseek-chat"},
                {"id": "deepseek-reasoner"},
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
            result = await fetch_models(config, providers={"deepseek"})

        expected = sorted(["deepseek:deepseek-chat", "deepseek:deepseek-reasoner"])
        assert result == expected, (
            "FAILS: fetch_models did not return live DeepSeek models.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}\n"
            "  Current: returns ['deepseek:deepseek-chat'] from _VERIFY_MODELS."
        )

    # ------------------------------------------------------------------
    # 3. Anthropic — must query /v1/models with x-api-key auth
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_queries_anthropic_api(self) -> None:
        """With connected={"anthropic"}, must query https://api.anthropic.com/v1/models.

        Mock HTTP 200 with ``{"data": [{"id":"claude-sonnet-4-5"},{"id":"claude-opus-4-5"}]}``.
        Assert returns both.

        FAILS: anthropic is NOT in the live_providers set; falls back to
        ``_VERIFY_MODELS`` returning ``["anthropic:claude-haiku-4-5"]`` only.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "anthropic": ProviderConfig(apiKey="sk-ant-test"),
            }
        )

        mock_response = {
            "data": [
                {"id": "claude-sonnet-4-5"},
                {"id": "claude-opus-4-5"},
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
            result = await fetch_models(config, providers={"anthropic"})

        expected = sorted(["anthropic:claude-sonnet-4-5", "anthropic:claude-opus-4-5"])
        assert result == expected, (
            "FAILS: fetch_models did not return live Anthropic models.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}\n"
            "  Current: returns ['anthropic:claude-haiku-4-5'] from _VERIFY_MODELS."
        )

    # ------------------------------------------------------------------
    # 4. Google — must query /v1beta/models with x-goog-api-key auth
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_queries_google_api(self) -> None:
        """With connected={"google-genai"}, must query Google's model endpoint.

        Mock HTTP 200 with Google-format ``{"models":[{"name":"models/gemini-2.5-pro","displayName":"Gemini 2.5 Pro"}]}``.
        Assert returns ``["google-genai:models/gemini-2.5-pro"]``.

        FAILS: google-genai is NOT in the live_providers set; falls back to
        ``_VERIFY_MODELS`` returning ``["google-genai:gemini-2.0-flash"]``.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "google-genai": ProviderConfig(apiKey="sk-test-google"),
            }
        )

        mock_response = {
            "models": [
                {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro"},
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
            result = await fetch_models(config, providers={"google-genai"})

        expected = ["google-genai:models/gemini-2.5-pro"]
        assert result == expected, (
            "FAILS: fetch_models did not return live Google models.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}\n"
            "  Current: returns ['google-genai:gemini-2.0-flash'] from _VERIFY_MODELS."
        )

    # ------------------------------------------------------------------
    # 5. _VERIFY_MODELS must no longer be importable
    # ------------------------------------------------------------------

    def test_fetch_models_no_verify_models_fallback(self) -> None:
        """``from pyharness.core.provider import _VERIFY_MODELS`` must raise ``ImportError``.

        The ``_VERIFY_MODELS`` dict is a hardcoded fallback — the SPEC mandates
        that every model ID comes from a provider's own API.  No static fallback.

        FAILS: ``_VERIFY_MODELS`` still exists at provider.py lines 293-303.
        """
        try:
            from pyharness.core.provider import _VERIFY_MODELS

            exists = True
        except ImportError:
            exists = False

        assert not exists, (
            "FAILS: ``_VERIFY_MODELS`` is still importable from provider.py.\n"
            "  Expected: ImportError — the dict must be removed entirely.\n"
            "  All model IDs must come from live provider APIs.\n"
            "  No hardcoded model list should exist anywhere.\n\n"
            "  Current _VERIFY_MODELS entries: openai, anthropic, deepseek,\n"
            "  google-genai, groq, mistralai, openrouter, together, ollama."
        )

    # ------------------------------------------------------------------
    # 6. Must use baseUrl from provider config
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_uses_base_url_from_provider_config(self) -> None:
        """With connected={"custom-provider"} and ``baseUrl: "https://my-llm.example.com/v1"``,
        fetch_models must query ``https://my-llm.example.com/v1/models``.

        FAILS: fetch_models does NOT read ``baseUrl`` from provider config
        for model discovery — it only knows hardcoded URLs for openrouter/ollama.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "custom-provider": ProviderConfig(
                    apiKey="sk-custom",
                    baseUrl="https://my-llm.example.com/v1",
                ),
            }
        )

        mock_response = {
            "data": [
                {"id": "custom-model-foo"},
                {"id": "custom-model-bar"},
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
            result = await fetch_models(config, providers={"custom-provider"})

        # Must have made an HTTP request to the custom base URL
        assert mock_client.get.called, (
            "FAILS: fetch_models must make an HTTP request for model discovery.\n"
            "  Current: custom-provider is not a live provider — it falls back to\n"
            "  _VERIFY_MODELS which has no entry for it, so returns an empty list."
        )

        if mock_client.get.called:
            call_url = mock_client.get.call_args[0][0]
            assert "my-llm.example.com" in call_url, (
                "FAILS: fetch_models must use baseUrl from provider config.\n"
                f"  Actual URL: {call_url}\n"
                f"  Expected: https://my-llm.example.com/v1/models\n"
                "  Current: only hardcoded URLs for openrouter/ollama."
            )

    # ------------------------------------------------------------------
    # 7. API failure returns empty list (no fallback)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_api_failure_returns_empty(self) -> None:
        """With connected={"openai"}, mock HTTP 401. Assert returns ``[]``.

        FAILS: current code falls back to ``_VERIFY_MODELS`` on non-live
        providers, returning ``["openai:gpt-4o-mini"]`` instead of ``[]``.
        When the API fails, we must not silently substitute hardcoded models.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "openai": ProviderConfig(apiKey="sk-bad-key"),
            }
        )

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        # Simulate 401 Unauthorized
        mock_get_response = MagicMock()
        mock_get_response.raise_for_status = MagicMock(
            side_effect=Exception("401 Unauthorized")
        )
        mock_client.get = AsyncMock(return_value=mock_get_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await fetch_models(config, providers={"openai"})

        assert result == [], (
            "FAILS: API failure must return empty list — no fallback.\n"
            f"  Got: {result}\n"
            "  Expected: []\n"
            "  Current: _VERIFY_MODELS fallback returns ['openai:gpt-4o-mini']\n"
            "  even when the live API call fails.  This is misleading — users\n"
            "  may try to use models from a broken config."
        )

    # ------------------------------------------------------------------
    # 8. Mixed providers — all from live APIs, no static models
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_models_mixed_providers_all_live(self) -> None:
        """With connected={"openai", "deepseek", "anthropic"}, mock all three APIs.
        Assert all models from all three appear, no duplicates, no static models.

        FAILS: only openrouter/ollama are treated as live.  openai, deepseek,
        and anthropic all fall back to single-model verifier entries.
        """
        from pyharness.core.provider import fetch_models

        config = PyHarnessConfig(
            provider={
                "openai": ProviderConfig(apiKey="sk-openai"),
                "deepseek": ProviderConfig(apiKey="sk-ds"),
                "anthropic": ProviderConfig(apiKey="sk-ant"),
            }
        )

        # Mock responses for each API
        mock_responses = {
            "https://api.openai.com/v1/models": {
                "data": [{"id": "gpt-5"}, {"id": "gpt-4o-mini"}]
            },
            "https://api.deepseek.com/v1/models": {
                "data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]
            },
            "https://api.anthropic.com/v1/models": {
                "data": [{"id": "claude-sonnet-4-5"}, {"id": "claude-opus-4-5"}]
            },
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        async def _mock_get(url: str, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value=mock_responses.get(url, {"data": []}))
            return resp

        mock_client.get = AsyncMock(side_effect=_mock_get)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await fetch_models(config, providers={"openai", "deepseek", "anthropic"})

        expected = sorted([
            "openai:gpt-5",
            "openai:gpt-4o-mini",
            "deepseek:deepseek-chat",
            "deepseek:deepseek-reasoner",
            "anthropic:claude-sonnet-4-5",
            "anthropic:claude-opus-4-5",
        ])

        assert result == expected, (
            "FAILS: fetch_models must query ALL connected providers' APIs.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}\n\n"
            "  Current: only openrouter and ollama are treated as 'live'.\n"
            "  OpenAI, DeepSeek, and Anthropic fall back to single-model\n"
            "  _VERIFY_MODELS entries instead of live API queries.\n"
            "  Expected behavior: every connected provider's API is queried\n"
            "  and all returned models are included."
        )
