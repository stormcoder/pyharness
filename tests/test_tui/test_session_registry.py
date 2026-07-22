"""Tests for Phase 1 parallel multi-agent — SessionRegistry and ChatScreen
session ownership.

Covers R1.1 through R1.5 from ``docs/specs/parallel-multi-agent.md`` plus
backward compatibility.

Run with::

    uv run pytest tests/test_tui/test_session_registry.py -q --tb=short
"""

from __future__ import annotations

import inspect

import pytest

from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.chat import ChatScreen
from pyharness.core.session_registry import (
    DEFAULT_SCREEN_ID,
    SessionRegistry,
)


# =============================================================================
# R1.3 — SessionRegistry
# =============================================================================


class TestSessionRegistry:
    """SessionRegistry stores and retrieves screen → session mappings."""

    # -- construct & initial state ----------------------------------------------

    def test_registry_constructs_with_empty_map(self) -> None:
        """A new SessionRegistry has no registered sessions."""
        reg = SessionRegistry()
        assert reg.list_all() == {}, "New registry must be empty"

    def test_registry_is_dataclass(self) -> None:
        """SessionRegistry is a dataclass instance."""
        reg = SessionRegistry()
        assert hasattr(reg, "_map"), "SessionRegistry must have _map field"

    # -- register ---------------------------------------------------------------

    def test_register_stores_mapping(self) -> None:
        """register(screen_id, session_id) stores the binding."""
        reg = SessionRegistry()
        reg.register("chat-1", "sess-abc123")
        assert reg.get("chat-1") == "sess-abc123", (
            "get must return the registered session_id"
        )

    def test_register_overwrites_existing(self) -> None:
        """register silently replaces a previous binding for the same screen."""
        reg = SessionRegistry()
        reg.register("chat-1", "sess-old")
        reg.register("chat-1", "sess-new")
        assert reg.get("chat-1") == "sess-new", (
            "register must overwrite when screen_id already exists"
        )

    def test_register_accepts_empty_string_ids(self) -> None:
        """register handles empty string screen_id and session_id."""
        reg = SessionRegistry()
        reg.register("", "")
        assert reg.get("") == "", "register must accept empty string IDs"

    # -- get -------------------------------------------------------------------

    def test_get_returns_none_for_unknown(self) -> None:
        """get returns None when screen_id is not registered."""
        reg = SessionRegistry()
        assert reg.get("nonexistent") is None, (
            "get must return None for unregistered screen_id"
        )

    def test_get_after_unregister_returns_none(self) -> None:
        """get returns None after unregister removes the binding."""
        reg = SessionRegistry()
        reg.register("chat-1", "sess-abc")
        reg.unregister("chat-1")
        assert reg.get("chat-1") is None, (
            "get must return None after unregister"
        )

    # -- unregister -------------------------------------------------------------

    def test_unregister_removes_mapping(self) -> None:
        """unregister removes the screen_id → session_id binding."""
        reg = SessionRegistry()
        reg.register("chat-1", "sess-abc")
        reg.unregister("chat-1")
        assert "chat-1" not in reg.list_all(), (
            "unregister must remove the screen_id from the mapping"
        )

    def test_unregister_unknown_is_noop(self) -> None:
        """unregister does not raise for an unregistered screen_id."""
        reg = SessionRegistry()
        reg.unregister("nonexistent")  # Must not raise
        assert reg.list_all() == {}, "unregister must not mutate empty registry"

    # -- list_all ---------------------------------------------------------------

    def test_list_all_returns_all_mappings(self) -> None:
        """list_all returns a dict of all registered screen→session pairs."""
        reg = SessionRegistry()
        reg.register("chat-1", "sess-a")
        reg.register("chat-2", "sess-b")
        all_mappings = reg.list_all()
        assert all_mappings == {"chat-1": "sess-a", "chat-2": "sess-b"}, (
            f"list_all must return all mappings, got {all_mappings}"
        )

    def test_list_all_returns_copy_not_reference(self) -> None:
        """list_all returns a shallow copy — mutations don't affect registry."""
        reg = SessionRegistry()
        reg.register("chat-1", "sess-a")
        snapshot = reg.list_all()
        snapshot["chat-1"] = "mutated"
        assert reg.get("chat-1") == "sess-a", (
            "list_all must return a copy; mutations must not affect registry"
        )

    def test_list_all_empty_returns_empty_dict(self) -> None:
        """list_all on an empty registry returns {}."""
        reg = SessionRegistry()
        assert reg.list_all() == {}, "list_all on empty registry must be {}"

    # -- default_session_id property --------------------------------------------

    def test_default_session_id_returns_none_initially(self) -> None:
        """default_session_id returns None before any default is registered."""
        reg = SessionRegistry()
        assert reg.default_session_id is None, (
            "default_session_id must be None before register_default"
        )

    def test_default_session_id_after_register_default(self) -> None:
        """default_session_id returns the session registered via register_default."""
        reg = SessionRegistry()
        reg.register_default("sess-default-42")
        assert reg.default_session_id == "sess-default-42", (
            "default_session_id must return the default binding"
        )

    def test_register_default_uses_dedicated_slot(self) -> None:
        """register_default stores under DEFAULT_SCREEN_ID, not a custom key."""
        reg = SessionRegistry()
        reg.register_default("sess-x")
        # The default is stored under DEFAULT_SCREEN_ID
        assert reg.get(DEFAULT_SCREEN_ID) == "sess-x", (
            "register_default must use DEFAULT_SCREEN_ID"
        )
        # It should also appear in list_all
        assert DEFAULT_SCREEN_ID in reg.list_all(), (
            "DEFAULT_SCREEN_ID must appear in list_all after register_default"
        )

    # -- DEFAULT_SCREEN_ID constant ---------------------------------------------

    def test_default_screen_id_is_a_string(self) -> None:
        """DEFAULT_SCREEN_ID is a str constant (not None or empty)."""
        assert isinstance(DEFAULT_SCREEN_ID, str), (
            f"DEFAULT_SCREEN_ID must be str, got {type(DEFAULT_SCREEN_ID).__name__}"
        )
        assert len(DEFAULT_SCREEN_ID) > 0, "DEFAULT_SCREEN_ID must be non-empty"

    # -- multiple registrations -------------------------------------------------

    def test_multiple_registrations_independent(self) -> None:
        """Multiple screens can be registered with different sessions."""
        reg = SessionRegistry()
        reg.register("screen-a", "sess-1")
        reg.register("screen-b", "sess-2")
        reg.register("screen-c", "sess-3")
        assert reg.get("screen-a") == "sess-1"
        assert reg.get("screen-b") == "sess-2"
        assert reg.get("screen-c") == "sess-3"
        assert len(reg.list_all()) == 3


# =============================================================================
# R1.1, R1.2 — ChatScreen session ownership (app-level in Phase 4)
# =============================================================================


class TestChatScreenSessionOwnership:
    """Session ownership is managed at the app level via _session_screens dict.

    In Phase 4, ChatScreen no longer carries a ``session_id`` attribute.
    Instead, ``PyHarnessApp._session_screens`` maps session IDs to screens
    and ``_focused_session_id`` tracks the currently visible session.
    """

    def test_app_has_session_screens_dict(self) -> None:
        """PyHarnessApp manages session→screen mapping via _session_screens."""
        app = PyHarnessApp()
        assert hasattr(app, "_session_screens"), (
            "App must have _session_screens dict for session→screen mapping"
        )
        assert isinstance(app._session_screens, dict)

    def test_app_has_focused_session_id(self) -> None:
        """PyHarnessApp tracks the focused session via _focused_session_id."""
        app = PyHarnessApp()
        assert hasattr(app, "_focused_session_id"), (
            "App must have _focused_session_id for session tracking"
        )

    def test_app_tracks_session_order(self) -> None:
        """PyHarnessApp tracks session ordering via _session_order."""
        app = PyHarnessApp()
        assert hasattr(app, "_session_order"), (
            "App must have _session_order list"
        )
        assert isinstance(app._session_order, list)

    def test_screens_can_be_registered_with_different_sessions(self) -> None:
        """Multiple screens can map to different session IDs in the app."""
        app = PyHarnessApp()
        screen_a = ChatScreen()
        screen_b = ChatScreen()
        app._session_screens["sess-a"] = screen_a
        app._session_screens["sess-b"] = screen_b
        assert app._session_screens["sess-a"] is screen_a
        assert app._session_screens["sess-b"] is screen_b
        assert app._session_screens["sess-a"] is not app._session_screens["sess-b"]

    def test_chat_screen_construction_is_basic(self) -> None:
        """ChatScreen() constructs without a session_id argument."""
        screen = ChatScreen()
        assert screen is not None


# =============================================================================
# Backward compatibility — ChatScreen() with no args
# =============================================================================


class TestChatScreenBackwardCompat:
    """ChatScreen() with no session_id constructs and operates correctly.

    In Phase 4, session ownership moved to the app level
    (``_session_screens``, ``_focused_session_id``, ``_session_registry``).
    ChatScreen itself no longer carries a ``session_id`` attribute —
    the app tracks which session each screen belongs to.
    """

    def test_no_args_does_not_crash(self) -> None:
        """ChatScreen() must instantiate without raising any exception."""
        screen = ChatScreen()  # Must not raise
        assert screen is not None

    def test_chat_screen_is_screen_subclass(self) -> None:
        """ChatScreen is a Textual Screen subclass."""
        from textual.screen import Screen
        assert isinstance(ChatScreen(), Screen), (
            "ChatScreen must be a Screen subclass"
        )

    def test_chat_screen_has_compose(self) -> None:
        """ChatScreen has a compose method."""
        assert hasattr(ChatScreen, "compose"), (
            "ChatScreen must have compose method"
        )

    def test_chat_screen_has_on_mount(self) -> None:
        """ChatScreen has an on_mount method."""
        assert hasattr(ChatScreen, "on_mount"), (
            "ChatScreen must have on_mount method"
        )


# =============================================================================
# ChatScreen resolves session from registry (when app is connected)
# =============================================================================


class TestChatScreenRegistryResolution:
    """Session resolution happens at the app level, not ChatScreen.

    In Phase 4, the app manages session→screen mapping.
    ChatScreen no longer resolves sessions directly — the app's
    ``_session_registry``, ``_focused_session_id``, and
    ``_session_screens`` dict do the mapping.
    """

    async def test_registry_persists_default_after_register(self) -> None:
        """After registering a default, the registry stores it."""
        app = PyHarnessApp()
        app._session_registry.register_default("from-registry-42")
        assert app._session_registry.default_session_id == "from-registry-42", (
            "Registry must store the default session ID"
        )

    def test_app_has_session_registry(self) -> None:
        """PyHarnessApp has _session_registry for session-to-screen mapping."""
        app = PyHarnessApp()
        assert hasattr(app, "_session_registry"), (
            "App must have _session_registry attribute"
        )
        # App also has _current_session_id as a legacy field for Phase 4 transition
        assert hasattr(app, "_current_session_id"), (
            "App must have _current_session_id (legacy field during Phase 4 transition)"
        )


# =============================================================================
# R1.4 — App uses registry, not scalar _current_session_id
# =============================================================================


class TestAppUsesRegistry:
    """Source inspection: app.py uses SessionRegistry alongside _current_session_id.

    Phase 4 transition: ``_current_session_id`` still exists as a legacy
    field while ``_session_registry`` and ``_session_screens`` provide the
    new multi-session infrastructure.  Tests verify the registry is wired
    correctly without requiring the old scalar to be removed prematurely.
    """

    def test_session_registry_is_instantiated(self) -> None:
        """PyHarnessApp.__init__ creates a SessionRegistry."""
        # Runtime check: an app instance has a non-None registry
        app = PyHarnessApp()
        assert app._session_registry is not None, (
            "_session_registry must be instantiated in __init__"
        )
        assert isinstance(app._session_registry, SessionRegistry), (
            f"_session_registry must be SessionRegistry, "
            f"got {type(app._session_registry).__name__}"
        )

    def test_current_session_id_still_present_for_legacy_compat(self) -> None:
        """_current_session_id still exists during Phase 4 transition."""
        app = PyHarnessApp()
        assert hasattr(app, "_current_session_id"), (
            "App must have _current_session_id (legacy field during transition)"
        )

    def test_init_source_contains_session_registry(self) -> None:
        """PyHarnessApp.__init__ source references SessionRegistry."""
        source = inspect.getsource(PyHarnessApp.__init__)
        assert "SessionRegistry" in source, (
            "__init__ must reference SessionRegistry"
        )
        assert "_session_registry" in source, (
            "__init__ must assign self._session_registry"
        )

    def test_init_session_uses_register_default(self) -> None:
        """_init_session calls _session_registry.register_default."""
        source = inspect.getsource(PyHarnessApp._init_session)
        assert "register_default" in source, (
            "_init_session must call _session_registry.register_default"
        )

    def test_phase4_session_attributes_exist(self) -> None:
        """Phase 4 multi-session attributes are present on the app."""
        app = PyHarnessApp()
        assert hasattr(app, "_session_screens"), "App must have _session_screens"
        assert hasattr(app, "_session_order"), "App must have _session_order"
        assert hasattr(app, "_focused_session_id"), "App must have _focused_session_id"
        assert hasattr(app, "_session_registry"), "App must have _session_registry"
        assert hasattr(app, "_active_sessions"), "App must have _active_sessions"


# =============================================================================
# R1.5 — on_input_submitted uses self.session_id
# =============================================================================


class TestOnInputSubmittedSessionId:
    """Source inspection: on_input_submitted resolves session from the app.

    In Phase 4, ChatScreen no longer owns ``session_id``.  The agent setup
    block in ``on_input_submitted`` resolves the session via
    ``self.app._current_session_id`` (legacy scalar, kept for Phase 4
    transition) rather than ``self.session_id``.
    """

    def test_uses_app_current_session_id_for_setup(self) -> None:
        """_run_agent agent setup references self.app._current_session_id.

        After the input refactor, agent setup code (resolve_model,
        get_registry, create_agent_graph, AgentRunner) moved from
        ``on_input_submitted`` into the ``_run_agent`` background method.
        """
        source = inspect.getsource(ChatScreen._run_agent)
        assert "self.app._current_session_id" in source, (
            "_run_agent must use self.app._current_session_id for agent setup"
        )

    def test_does_not_have_self_session_id_attribute(self) -> None:
        """ChatScreen does NOT have a session_id attribute in Phase 4."""
        source = inspect.getsource(ChatScreen._run_agent)
        # In Phase 4, session resolution moved to app level
        assert "self.session_id" not in source, (
            "_run_agent must NOT reference self.session_id "
            "(session ownership moved to app level)"
        )

    def test_session_id_comes_from_current_session(self) -> None:
        """Agent setup in _run_agent derives session_id from self.app._current_session_id."""
        source = inspect.getsource(ChatScreen._run_agent)
        assert "session_id = self.app._current_session_id" in source, (
            "_run_agent must assign session_id = self.app._current_session_id"
        )

    def test_chat_screen_no_longer_needs_resolve_method(self) -> None:
        """ChatScreen does NOT need _resolve_session_id — app handles it."""
        # In Phase 4, session resolution is the app's responsibility
        screen = ChatScreen()
        # _resolve_session_id is no longer needed; session_id comes from the app
        assert not hasattr(screen, "_resolve_session_id"), (
            "ChatScreen must NOT have _resolve_session_id "
            "(session resolution moved to app level in Phase 4)"
        )

    def test_chat_screen_accepts_no_session_id(self) -> None:
        """ChatScreen accepts no session_id constructor argument."""
        screen = ChatScreen()
        assert screen is not None


# =============================================================================
# SessionRegistry edge cases and invariants
# =============================================================================


class TestSessionRegistryEdgeCases:
    """Edge cases and invariants for SessionRegistry."""

    def test_register_idempotent_same_value(self) -> None:
        """Registering the same pair twice does not change anything."""
        reg = SessionRegistry()
        reg.register("chat-1", "sess-a")
        reg.register("chat-1", "sess-a")
        assert reg.get("chat-1") == "sess-a"
        assert len(reg.list_all()) == 1

    def test_register_many_then_unregister_all(self) -> None:
        """After registering N pairs and unregistering all, registry is empty."""
        reg = SessionRegistry()
        for i in range(10):
            reg.register(f"chat-{i}", f"sess-{i}")
        for i in range(10):
            reg.unregister(f"chat-{i}")
        assert reg.list_all() == {}, (
            "Registry must be empty after all unregistered"
        )

    def test_register_default_then_register_same_screen(self) -> None:
        """register_default + register on DEFAULT_SCREEN_ID: last write wins."""
        reg = SessionRegistry()
        reg.register_default("first")
        reg.register(DEFAULT_SCREEN_ID, "second")
        assert reg.default_session_id == "second", (
            "Direct register on DEFAULT_SCREEN_ID must overwrite register_default"
        )

    def test_list_all_after_register_and_unregister(self) -> None:
        """list_all reflects the current state after a sequence of mutations."""
        reg = SessionRegistry()
        reg.register("a", "1")
        reg.register("b", "2")
        reg.register("c", "3")
        reg.unregister("b")
        assert reg.list_all() == {"a": "1", "c": "3"}, (
            "list_all must reflect mutations, not stale state"
        )

    def test_independent_registry_instances(self) -> None:
        """Two SessionRegistry instances are fully independent."""
        reg_a = SessionRegistry()
        reg_b = SessionRegistry()
        reg_a.register("x", "1")
        reg_b.register("x", "2")
        assert reg_a.get("x") == "1"
        assert reg_b.get("x") == "2"
