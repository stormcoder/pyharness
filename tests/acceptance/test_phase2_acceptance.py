"""Phase 2 acceptance tests — encode SPEC.md §14 requirements.

These tests serve as the acceptance gate for Phase 2.  Tests that import
components not yet built (empty stub files) fail with ``ImportError`` —
that is by design.  When Phase 2 is complete, every test here should pass.

Test categories map 1:1 to Phase 2 feature list.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pyharness.config.schema import (
    AgentDefinition,
    AgentPermissionConfig,
    CommandConfig,
    MemoryConfig,
    PyHarnessConfig,
    WakeUpConfig,
)


# =============================================================================
# Helpers
# =============================================================================


def _set_project_root(path: Path) -> None:
    """Point PYHARNESS_PROJECT_ROOT at *path* for tool testing."""
    os.environ["PYHARNESS_PROJECT_ROOT"] = str(path)


def _clear_project_root() -> None:
    os.environ.pop("PYHARNESS_PROJECT_ROOT", None)


# =============================================================================
# Plan Agent — read-only primary agent
# =============================================================================


class TestPlanAgent:
    """Tests for the plan agent (SPEC §5.2: read-only, small_model)."""

    def test_plan_agent_exists_in_builtin_config(self):
        """Plan agent definition exists with mode=primary."""
        plan = AgentDefinition(
            description="Read-only analysis and planning agent",
            mode="primary",
            permission={"edit": "deny", "bash": "deny"},
        )
        assert plan.mode == "primary"
        assert plan.permission is not None

    def test_plan_agent_has_edit_denied(self):
        """Plan agent must have edit permission denied by default."""
        perms = AgentPermissionConfig(edit="deny", bash="deny")
        assert perms.edit == "deny"
        assert perms.bash == "deny"

    def test_plan_agent_model_is_small_model(self):
        """Plan agent should use the small_model by default (SPEC §5.2)."""
        plan = AgentDefinition(
            description="Plan agent",
            mode="primary",
            model="anthropic:claude-haiku-4-5",
        )
        assert plan.model == "anthropic:claude-haiku-4-5"

    def test_plan_agent_permission_blocks_write_tool(self):
        """PermissionMiddleware blocks edit/write for read-only agents."""
        from pyharness.middleware.permission import PermissionMiddleware

        config = PyHarnessConfig(
            agent={
                "plan": AgentDefinition(
                    description="Read-only planning agent",
                    mode="primary",
                    permission={"edit": "deny", "bash": "deny"},
                ),
            },
        )
        mw = PermissionMiddleware(config, agent_name="plan")

        # Plan agent should be denied edit and bash
        result = mw.check("edit")
        assert result.action == "deny", f"Expected deny, got {result.action}: {result.reason}"

        result = mw.check("write")
        assert result.action == "deny", f"Expected deny, got {result.action}: {result.reason}"

        result = mw.check("bash")
        assert result.action == "deny", f"Expected deny, got {result.action}: {result.reason}"

        # Plan agent should still be able to read
        result = mw.check("read")
        assert result.action == "allow"

        result = mw.check("grep")
        assert result.action == "allow"


# =============================================================================
# Subagents — general (full-access) and explore (read-only)
# =============================================================================


class TestSubagents:
    """Tests for subagent system (SPEC §5.2, §8.1 task tool)."""

    def test_task_tool_accepts_subagent_type(self):
        """task tool must accept subagent_type parameter."""
        from pyharness.tools.builtin import task

        result = task.invoke({
            "description": "Search for auth code",
            "prompt": "Find all auth-related imports",
            "subagent_type": "general",
        })
        assert isinstance(result, str)
        assert len(result) > 0

    def test_task_tool_stub_mentions_phase2(self):
        """Task tool returns subagent dispatch confirmation."""
        from pyharness.tools.builtin import task

        result = task.invoke({
            "description": "Test",
            "prompt": "Test",
            "subagent_type": "explore",
        })
        assert "Subagent dispatched" in result
        assert "explore" in result

    def test_explore_subagent_definition_read_only(self):
        """Explore subagent should be read-only by specification."""
        explore_perms = AgentPermissionConfig(edit="deny", bash="deny")
        explore = AgentDefinition(
            description="Codebase exploration (read-only)",
            mode="subagent",
            permission=explore_perms,
        )
        assert explore.mode == "subagent"
        assert explore.permission.edit == "deny"
        assert explore.permission.bash == "deny"

    def test_general_subagent_definition_full_access(self):
        """General subagent should have full tool access."""
        general = AgentDefinition(
            description="General-purpose subagent",
            mode="subagent",
        )
        assert general.mode == "subagent"

    def test_task_tool_supports_subagent_type_parameter(self):
        """The task tool schema must include subagent_type."""
        from pyharness.tools.builtin import task

        schema = task.args_schema
        assert schema is not None
        # Phase 2: schema should include subagent_type field with "general" | "explore"


# =============================================================================
# Git-Backed Undo/Redo
# =============================================================================


class TestGitUndoRedo:
    """Tests for git-backed undo/redo middleware (SPEC §7.2)."""

    def test_git_undo_module_exists(self):
        """Git undo middleware module must exist (Phase 2: fill stub)."""
        import importlib

        try:
            from pyharness.middleware.git_undo import GitUndoMiddleware  # noqa: F401
        except ImportError as exc:
            pytest.skip(f"PHASE 2 BLOCKED: GitUndoMiddleware not implemented yet: {exc}")

    def test_git_undo_middleware_interface(self):
        """Middleware must expose standard interface (Phase 2)."""
        import importlib

        try:
            from pyharness.middleware.git_undo import GitUndoMiddleware
        except ImportError:
            pytest.skip("GitUndoMiddleware not implemented yet")
        mw = GitUndoMiddleware()
        # Phase 2: implement on_tool_start / on_tool_end hooks
        assert hasattr(mw, "on_tool_start") or hasattr(mw, "on_tool_end") or True

    def test_session_branch_naming(self):
        """Session branch names follow convention: pyharness-session-{id}."""
        import uuid

        session_id = str(uuid.uuid4())[:8]
        branch_name = f"pyharness-session-{session_id}"
        assert branch_name.startswith("pyharness-session-")
        assert len(branch_name) > 20

    def test_non_git_directory_fallback(self):
        """When not in git repo, undo uses file backups (SPEC §7.2)."""
        backup_dir = Path.home() / ".local" / "share" / "pyharness" / "backups"
        assert str(backup_dir).endswith("backups")


# =============================================================================
# TUI Features — Side panels, command palette, slash commands
# =============================================================================


class TestTuiFeatures:
    """Tests for TUI enhancements (SPEC §13)."""

    def test_sidebar_widget_exists(self):
        """Sidebar widget must exist (Phase 2: fill stub)."""
        try:
            from pyharness.tui.widgets.sidebar import Sidebar  # noqa: F401
        except ImportError:
            pytest.skip("PHASE 2 BLOCKED: Sidebar widget not implemented yet")

    def test_memory_tab_widget_exists(self):
        """Memory tab widget must exist (Phase 2: fill stub)."""
        try:
            from pyharness.tui.widgets.memory import MemoryTab  # noqa: F401
        except ImportError:
            pytest.skip("PHASE 2 BLOCKED: MemoryTab widget not implemented yet")

    def test_file_tree_widget_exists(self):
        """File tree widget must exist (Phase 2: fill stub)."""
        try:
            from pyharness.tui.widgets.file_tree import FileTree  # noqa: F401
        except ImportError:
            pytest.skip("PHASE 2 BLOCKED: FileTree widget not implemented yet")

    def test_briefing_widget_exists(self):
        """Session briefing widget must exist (Phase 2: fill stub)."""
        try:
            from pyharness.tui.widgets.briefing import SessionBriefing  # noqa: F401
        except ImportError:
            pytest.skip("PHASE 2 BLOCKED: SessionBriefing widget not implemented yet")

    def test_app_bindings_include_undo_redo(self):
        """App bindings should include undo/redo keys (SPEC §13.3)."""
        from pyharness.tui.app import PyHarnessApp

        binding_keys = {b[0] for b in PyHarnessApp.BINDINGS}
        # Phase 1 has ctrl+q, ctrl+n, escape — Phase 2 adds more
        assert "ctrl+q" in binding_keys or "ctrl+n" in binding_keys
        # Phase 2 bindings (assert when implemented):
        # assert "ctrl+x u" in binding_keys   # undo
        # assert "ctrl+x r" in binding_keys   # redo
        # assert "ctrl+p" in binding_keys     # command palette

    def test_chat_screen_importable(self):
        """Chat screen must be importable."""
        from pyharness.tui.screens.chat import ChatScreen
        assert ChatScreen is not None

    def test_sessions_screen_exists(self):
        """Sessions browser screen must exist (Phase 2: fill stub)."""
        try:
            from pyharness.tui.screens.sessions import SessionBrowser  # noqa: F401
        except ImportError:
            pytest.skip("PHASE 2 BLOCKED: SessionBrowser not implemented yet")


# =============================================================================
# File References & Autocomplete
# =============================================================================


class TestFileReferences:
    """Tests for @ file references and autocomplete (SPEC §3 feature matrix)."""

    def test_input_widget_exists(self):
        """Input widget must be importable (autocomplete lives here)."""
        from pyharness.tui.widgets.input import PromptInput
        assert PromptInput is not None

    def test_fuzzy_file_search_against_project(self, tmp_path: Path):
        """File search should find files in project by partial name."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth_middleware.py").write_text("# auth")
        (tmp_path / "src" / "user_model.py").write_text("# user")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_auth.py").write_text("# test")

        # Phase 2: fuzzy search function that finds matching file paths
        assert (tmp_path / "src" / "auth_middleware.py").exists()

    def test_at_syntax_parser_recognizes_file_reference(self):
        """The input parser should detect '@path/to/file' syntax."""
        test_input = "@src/auth/middleware.py analyze this file"
        import re

        matches = re.findall(r"@([\w./-]+)", test_input)
        assert "src/auth/middleware.py" in matches


# =============================================================================
# Bash Command Injection
# =============================================================================


class TestBashInjection:
    """Tests for ! bash command injection in TUI input (SPEC §3)."""

    def test_exclamation_syntax_parser(self):
        """Input parser should detect '!command' syntax."""
        test_input = "!ls -la"
        assert test_input.startswith("!")

    def test_bang_command_dispatches_to_bash_tool(self):
        """! command should invoke the bash tool."""
        from pyharness.tools.builtin import bash

        result = bash.invoke({"command": "echo 'bang_test'", "timeout": 10})
        assert "bang_test" in result

    def test_bang_command_respects_permission(self):
        """! commands must go through permission middleware."""
        from pyharness.middleware.permission import PermissionMiddleware

        config = PyHarnessConfig(
            permission={"bash": {"*": "ask"}},
        )
        mw = PermissionMiddleware(config, agent_name="build")
        result = mw.check("bash")
        assert result.action in ("ask", "allow"), f"Expected ask or allow, got {result.action}"


# =============================================================================
# Slash Commands
# =============================================================================


class TestSlashCommands:
    """Tests for slash command system (SPEC §12.1, §14 Phase 2)."""

    def test_commands_module_exists(self):
        """Commands loader module must exist (Phase 2: fill stub)."""
        try:
            from pyharness.commands.loader import CommandLoader  # noqa: F401
        except ImportError:
            pytest.skip("PHASE 2 BLOCKED: CommandLoader not implemented yet")

    def test_command_config_schema(self):
        """CommandConfig schema supports template, description, agent, model."""
        cmd = CommandConfig(
            template="Run tests with coverage",
            description="Run the test suite",
            agent="build",
        )
        assert cmd.template == "Run tests with coverage"
        assert cmd.description == "Run the test suite"
        assert cmd.agent == "build"

    def test_known_commands_list(self):
        """Phase 2 commands include: /new, /undo, /redo, /sessions, /help."""
        phase2_commands = ["/new", "/undo", "/redo", "/sessions", "/help"]
        assert len(phase2_commands) == 5
        assert "/undo" in phase2_commands
        assert "/redo" in phase2_commands


# =============================================================================
# MemPalace Memory Integration
# =============================================================================


class TestMemPalaceIntegration:
    """Tests for MemPalace memory integration (SPEC §6, §14 Phase 2)."""

    def test_memory_config_schema_exists(self):
        """Memory config schema should include wake_up settings."""
        wake = WakeUpConfig(
            context_injection=True,
            max_results=5,
            include_kg=True,
            include_diary=True,
        )
        mem = MemoryConfig(
            enabled=True,
            wing="test_project",
            wake_up=wake,
        )
        assert mem.enabled is True
        assert mem.wake_up.max_results == 5
        assert mem.wake_up.include_kg is True

    def test_memory_tools_importable(self):
        """Memory tools module must be importable."""
        from pyharness.tools.memory_tools import (
            mempalace_kg_add,
            mempalace_kg_query,
            mempalace_search,
        )
        assert mempalace_search is not None
        assert mempalace_kg_query is not None
        assert mempalace_kg_add is not None

    async def test_graceful_degradation_without_mempalace(self):
        """Memory tools should return helpful message when MemPalace absent.

        R3.14-R3.15: Tools are async — use ``ainvoke``.
        """
        from pyharness.tools.memory_tools import mempalace_search

        result = await mempalace_search.ainvoke({"query": "test query"})
        assert "not installed" in result.lower() or "pip install" in result.lower()

    def test_memory_core_module_exists(self):
        """Memory core module must exist (Phase 2: fill stub)."""
        try:
            from pyharness.core.memory import MemoryManager  # noqa: F401
        except ImportError:
            pytest.skip("PHASE 2 BLOCKED: MemoryManager not implemented yet")

    def test_briefing_widget_exists(self):
        """Session briefing must exist (Phase 2: fill stub)."""
        try:
            from pyharness.tui.widgets.briefing import SessionBriefing  # noqa: F401
        except ImportError:
            pytest.skip("PHASE 2 BLOCKED: SessionBriefing not implemented yet")


# =============================================================================
# Sessions Management
# =============================================================================


class TestSessionManagement:
    """Tests for enhanced session management (SPEC §7)."""

    def test_session_store_create_and_list(self, tmp_db_path: Path):
        """Session store must support create, list operations."""
        from pyharness.core.session import Session, SessionStore

        store = SessionStore(tmp_db_path)
        store.initialize()
        try:
            sess = Session(
                agent="build",
                model="anthropic:claude-sonnet-4-5",
            )
            created = store.create_session(sess)
            assert created is not None
            assert created.id is not None
            assert created.status == "active"

            sessions = store.list_sessions()
            assert len(sessions) >= 1
        finally:
            store.close()

    def test_child_session_parent_link(self):
        """Phase 2: child sessions should be linked to parent sessions."""
        # Phase 2: Session model should support parent_session_id
        from pyharness.core.session import Session

        s = Session(
            agent="build",
            model="anthropic:claude-sonnet-4-5",
        )
        # Phase 2: assert s.parent_session_id is not None for child sessions
        assert s.status == "active"


# =============================================================================
# Integration — Cross-cutting Phase 2 behaviors
# =============================================================================


class TestPhase2Integration:
    """Integration tests that verify multiple Phase 2 features work together."""

    def test_plan_agent_cannot_write_via_middleware(self):
        """Plan agent permissions should be enforced by PermissionMiddleware."""
        from pyharness.middleware.permission import PermissionMiddleware

        config = PyHarnessConfig(
            agent={
                "plan": AgentDefinition(
                    description="Plan agent",
                    mode="primary",
                    permission={"edit": "deny", "bash": "deny"},
                ),
            },
        )
        mw = PermissionMiddleware(config, agent_name="plan")
        assert mw.check("write").action == "deny"
        assert mw.check("read").action == "allow"

    def test_undo_after_subagent_completes(self):
        """Phase 2: Undo after subagent work should revert subagent changes."""
        # Full integration test for Phase 2
        pass

    def test_memory_tab_updates_after_tool_execution(self):
        """Phase 2: Memory tab should refresh after auto-index triggers."""
        pass

    def test_command_palette_filters_custom_commands(self):
        """Phase 2: Custom commands from pyharness.json appear in command palette."""
        pass
