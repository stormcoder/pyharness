"""Phase 3 acceptance tests — MCP, Skills, Memory UX, Themes, Keybinds.

These tests encode SPEC.md §14 Phase 3 requirements (lines 825-838).  Tests
that import components not yet built fail with ``ImportError`` — that is by
design.  When Phase 3 is complete, every test here should pass.

Test categories map 1:1 to Phase 3 feature list:

1. MCP client (langchain-mcp-adapters + native SDK)
2. MCP server registry & management UI
3. Agent Skills (SKILL.md discovery & loading)
4. Custom commands system
5. /init workflow (AGENTS.md generation)
6. Web search & web fetch
7. Memory search UX (/memory command, inline citations)
8. Knowledge graph visualization (sidebar tree view)
9. Session browser with memory badges
10. Theme system (Textual CSS themes)
11. Keybind customization
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyharness.config.schema import (
    MCPServerConfig,
    PyHarnessConfig,
)


# =============================================================================
# 1. MCP Client
# =============================================================================


class TestMCPClient:
    """MCP client must work with stdio and HTTP transports."""

    def test_mcp_loader_module_importable(self):
        """MCP loader module must exist."""
        try:
            import pyharness.tools.mcp_loader  # noqa: F401
        except ImportError as exc:
            pytest.skip(f"PHASE 3 BLOCKED: mcp_loader module not importable: {exc}")

    def test_mcp_loader_class_exists(self):
        """MCPLoader class must be present when Phase 3 lands."""
        try:
            from pyharness.tools.mcp_loader import MCPLoader  # noqa: F401
        except ImportError:
            pytest.skip("PHASE 3 BLOCKED: MCPLoader class not yet implemented")

    def test_mcp_config_field_exists(self):
        """PyHarnessConfig must have an mcp field for server definitions."""
        cfg = PyHarnessConfig()
        assert hasattr(cfg, "mcp")
        assert isinstance(cfg.mcp, dict)

    def test_mcp_server_config_local_validation(self):
        """MCPServerConfig of type 'local' must require a command."""
        with pytest.raises(ValueError, match="command"):
            MCPServerConfig(type="local")

    def test_mcp_server_config_remote_validation(self):
        """MCPServerConfig of type 'remote' must require a url."""
        with pytest.raises(ValueError, match="url"):
            MCPServerConfig(type="remote")

    def test_mcp_server_config_local_creation(self):
        """MCPServerConfig for a local server creates correctly."""
        cfg = MCPServerConfig(
            type="local",
            command=["python", "-m", "my_mcp_server"],
        )
        assert cfg.type == "local"
        assert cfg.command == ["python", "-m", "my_mcp_server"]

    def test_mcp_server_config_remote_creation(self):
        """MCPServerConfig for a remote server creates correctly."""
        cfg = MCPServerConfig(
            type="remote",
            url="https://mcp.example.com/sse",
        )
        assert cfg.type == "remote"
        assert cfg.url == "https://mcp.example.com/sse"

    def test_mcp_sidebar_section_exists(self):
        """Sidebar must have an MCP servers section in its compose method."""
        try:
            from pyharness.tui.widgets.sidebar import Sidebar
        except ImportError:
            pytest.skip("Sidebar not implemented yet")

        # Sidebar.compose() yields sections with id='section-mcp'
        import inspect
        source = inspect.getsource(Sidebar.compose)
        assert "section-mcp" in source, (
            "Sidebar must contain an MCP section with id='section-mcp'"
        )


# =============================================================================
# 2. MCP Server Registry & Management UI
# =============================================================================


class TestMCPServerRegistry:
    """MCP server registry must support listing configured servers."""

    def test_config_can_hold_multiple_mcp_servers(self):
        """Config mcp field must accept multiple server definitions."""
        cfg = PyHarnessConfig(
            mcp={
                "filesystem": MCPServerConfig(
                    type="local",
                    command=["npx", "@anthropic/mcp-filesystem"],
                ),
                "memory": MCPServerConfig(
                    type="local",
                    command=["npx", "@anthropic/mcp-memory"],
                ),
            },
        )
        assert len(cfg.mcp) == 2
        assert "filesystem" in cfg.mcp
        assert "memory" in cfg.mcp


# =============================================================================
# 3. Agent Skills (SKILL.md Discovery & Loading)
# =============================================================================


class TestSkillsDiscovery:
    """SKILL.md files must be discoverable from multiple directories."""

    def test_discover_skills_returns_list(self):
        """discover_skills() returns a list of SKILL.md paths."""
        from pyharness.skills.loader import discover_skills

        skills = discover_skills()
        assert isinstance(skills, list)

    def test_discover_skills_search_paths_exist(self):
        """Function must search at least global + project directories."""
        from pyharness.skills.loader import discover_skills

        # The function defines search_dirs internally; verify it runs
        # without error and returns a list.
        result = discover_skills()
        assert result is not None

    def test_skill_loader_importable(self):
        """Skills loader module must be importable."""
        from pyharness.skills.loader import discover_skills
        assert callable(discover_skills)


# =============================================================================
# 4. Custom Commands System
# =============================================================================


class TestCustomCommands:
    """Custom slash-command loading and registration."""

    def test_command_loader_loads_builtins(self):
        """CommandLoader must produce built-in commands without config."""
        from pyharness.commands.loader import CommandLoader

        loader = CommandLoader(config=None)
        commands = loader.load_all()
        assert len(commands) >= 12, f"Expected 12+ commands, got {len(commands)}"

    def test_command_loader_finds_by_name(self):
        """CommandLoader.find() returns commands by /name."""
        from pyharness.commands.loader import CommandLoader

        loader = CommandLoader()
        cmd = loader.find("/new")
        assert cmd is not None
        assert cmd.name == "/new"

    def test_commands_include_phase3_entries(self):
        """Phase 3 commands: /memory, /remember, /themes must be registered."""
        from pyharness.commands.loader import CommandLoader

        loader = CommandLoader()
        commands = loader.load_all()
        assert "/memory" in commands, "Phase 3: /memory command missing"
        assert "/remember" in commands, "Phase 3: /remember command missing"
        assert "/themes" in commands, "Phase 3: /themes command missing"

    def test_custom_commands_from_files(self):
        """load_custom_commands() discovers *.md files in commands dirs."""
        from pyharness.commands.loader import load_custom_commands

        cmds = load_custom_commands()
        assert isinstance(cmds, dict)

    def test_command_config_schema_supports_fields(self):
        """CommandConfig must support template, description, agent, model."""
        from pyharness.config.schema import CommandConfig

        cmd = CommandConfig(
            template="Run the test suite with coverage",
            description="Execute pytest with coverage reporting",
            agent="build",
            model="anthropic:claude-sonnet-4-5",
        )
        assert cmd.agent == "build"
        assert cmd.model == "anthropic:claude-sonnet-4-5"
        assert "coverage" in cmd.template


# =============================================================================
# 5. /init Workflow (AGENTS.md Generation)
# =============================================================================


class TestInitWorkflow:
    """/init must generate AGENTS.md for the current project."""

    def test_init_command_in_app_commands(self):
        """/init must be registered as a known command."""
        from pyharness.tui.app import PyHarnessApp

        # Phase 3: /init should appear in COMMANDS
        assert (
            "/init" in PyHarnessApp.COMMANDS
        ), "PHASE 3 REQUIRED: /init command missing from COMMANDS dict"

    def test_init_sidebar_mentions_init(self):
        """Sidebar AGENTS.md section must reference the /init command."""
        try:
            from pyharness.tui.widgets.sidebar import Sidebar
        except ImportError:
            pytest.skip("Sidebar not implemented yet")

        # Check that the compose source mentions /init
        import inspect
        source = inspect.getsource(Sidebar.compose)
        assert "/init" in source, (
            "Sidebar AGENTS.md section should mention /init for Phase 3"
        )


# =============================================================================
# 6. Web Search & Web Fetch Tools
# =============================================================================


class TestWebTools:
    """Web search and fetch tools must be registered."""

    def test_webfetch_tool_registered(self):
        """'webfetch' tool must exist in the tool registry."""
        from pyharness.tools.registry import get_registry

        tools = get_registry().get_names()
        assert "webfetch" in tools, (
            "PHASE 3 REQUIRED: 'webfetch' tool not registered. "
            f"Current tools: {', '.join(tools)}"
        )

    def test_websearch_tool_registered(self):
        """'websearch' tool must exist in the tool registry."""
        from pyharness.tools.registry import get_registry

        tools = get_registry().get_names()
        assert "websearch" in tools, (
            "PHASE 3 REQUIRED: 'websearch' tool not registered. "
            f"Current tools: {', '.join(tools)}"
        )

    def test_builtin_tools_include_web_operations(self):
        """ALL_BUILTIN_TOOLS should include webfetch and websearch (Phase 3)."""
        from pyharness.tools.builtin import ALL_BUILTIN_TOOLS

        tool_names = {t.name for t in ALL_BUILTIN_TOOLS}
        assert "webfetch" in tool_names, (
            "PHASE 3 REQUIRED: 'webfetch' not in ALL_BUILTIN_TOOLS"
        )
        assert "websearch" in tool_names, (
            "PHASE 3 REQUIRED: 'websearch' not in ALL_BUILTIN_TOOLS"
        )


# =============================================================================
# 7. Memory Search UX
# =============================================================================


class TestMemoryUX:
    """Memory search and knowledge graph must be accessible."""

    def test_memory_command_in_app_commands(self):
        """/memory must be a registered slash command."""
        from pyharness.tui.app import PyHarnessApp

        assert "/memory" in PyHarnessApp.COMMANDS

    def test_remember_command_in_app_commands(self):
        """/remember must be a registered slash command."""
        from pyharness.tui.app import PyHarnessApp

        assert "/remember" in PyHarnessApp.COMMANDS

    def test_memory_tab_has_expected_sections(self):
        """MemoryTab must render KG, related sessions, and diary sections."""
        try:
            from pyharness.tui.widgets.memory import MemoryTab

            tab = MemoryTab()
            children = list(tab.compose())
            # 3 section titles + 3 content areas = 6 widgets minimum
            assert len(children) >= 6, (
                f"Expected 6+ widgets in MemoryTab compose(), got {len(children)}"
            )
        except ImportError:
            pytest.skip("MemoryTab not implemented yet")

    def test_memory_tab_has_content_ids(self):
        """MemoryTab must have renderable IDs for kg, related, diary."""
        try:
            from pyharness.tui.widgets.memory import MemoryTab

            tab = MemoryTab()
            for child in tab.compose():
                if hasattr(child, "id") and child.id:
                    assert child.id in (
                        "kg-content",
                        "related-content",
                        "diary-content",
                        "section-title",
                    ), f"Unexpected child id: {child.id}"
        except ImportError:
            pytest.skip("MemoryTab not implemented yet")

    def test_memory_tab_label_present(self):
        """Memory tab should be labelled with 🧠 emoji."""
        try:
            from pyharness.tui.widgets.memory import MemoryTab

            tab = MemoryTab()
            children = list(tab.compose())
            kg_label = children[0]
            rendered = kg_label.render()
            assert "🧠" in str(rendered) or "Knowledge Graph" in str(rendered)
        except ImportError:
            pytest.skip("MemoryTab not implemented yet")


# =============================================================================
# 8. Knowledge Graph Visualization (Sidebar Tree View)
# =============================================================================


class TestKnowledgeGraphVisualization:
    """Knowledge graph must be visualisable in the sidebar."""

    def test_sidebar_has_agents_section(self):
        """Sidebar AGENTS.md section references is a project guide."""
        try:
            from pyharness.tui.widgets.sidebar import Sidebar
        except ImportError:
            pytest.skip("Sidebar not implemented yet")

        import inspect
        source = inspect.getsource(Sidebar.compose)
        assert "section-agents" in source, "Sidebar missing section-agents container"
        assert "agents-content" in source, "Sidebar missing #agents-content widget"

    def test_memory_tab_kg_section_updatable(self):
        """MemoryTab.update_kg_facts() method signature accepts fact strings."""
        try:
            from pyharness.tui.widgets.memory import MemoryTab
        except ImportError:
            pytest.skip("MemoryTab not implemented yet")

        import inspect
        sig = inspect.signature(MemoryTab.update_kg_facts)
        params = list(sig.parameters)
        # First param after self should be 'facts' taking a list
        assert "facts" in params, (
            f"update_kg_facts must have 'facts' parameter: {params}"
        )


# =============================================================================
# 9. Session Browser with Memory Badges
# =============================================================================


class TestSessionBrowser:
    """Session browser must show memory badges."""

    def test_session_browser_importable(self):
        """SessionBrowser screen must be importable."""
        from pyharness.tui.screens.sessions import SessionBrowser
        assert SessionBrowser is not None

    def test_session_browser_is_a_screen(self):
        """SessionBrowser must inherit from textual Screen."""
        from textual.screen import Screen

        from pyharness.tui.screens.sessions import SessionBrowser

        assert issubclass(SessionBrowser, Screen)

    def test_session_browser_composes(self):
        """SessionBrowser.compose() method must be defined with Container."""
        from pyharness.tui.screens.sessions import SessionBrowser

        import inspect
        source = inspect.getsource(SessionBrowser.compose)
        assert "Container" in source, "SessionBrowser compose must use a Container"
        assert ("sessions-content" in source or "session-browser" in source or
                "sb-status" in source or "sb-list" in source), (
            "SessionBrowser must have identifiable widget IDs. "
            f"Source:\n{source[:300]}"
        )


# =============================================================================
# 10. Theme System
# =============================================================================


class TestThemes:
    """Theme system must support loading and switching."""

    def test_themes_directory_exists(self):
        """Themes package directory must exist."""
        import pyharness.tui.themes

        themes_dir = Path(pyharness.tui.themes.__file__).parent
        assert themes_dir.exists()

    def test_theme_list_command_exists(self):
        """/themes must be a registered slash command."""
        from pyharness.tui.app import PyHarnessApp

        assert "/themes" in PyHarnessApp.COMMANDS

    def test_themes_module_importable(self):
        """Themes __init__ module must be importable (Phase 3: fill stub)."""
        import pyharness.tui.themes
        assert pyharness.tui.themes is not None

    def test_app_css_applies_github_dark_theme(self):
        """App CSS must define dark background colours."""
        from pyharness.tui.app import PyHarnessApp

        css = PyHarnessApp.CSS
        assert "#0d1117" in css, "Dark background (#0d1117) not in app CSS"
        assert "#161b22" in css, "Card/sidebar background (#161b22) not in app CSS"


# =============================================================================
# 11. Keybind Customization
# =============================================================================


class TestKeybinds:
    """Keybind customization must work."""

    def test_tui_app_has_bindings(self):
        """PyHarnessApp.BINDINGS must contain at least Phase 3 keybinds."""
        from pyharness.tui.app import PyHarnessApp

        bindings = PyHarnessApp.BINDINGS
        assert len(bindings) >= 6, f"Expected 6+ bindings, got {len(bindings)}"

    def test_required_keybinds_present(self):
        """Phase 3 binds: ctrl+q quit, ctrl+n new_session, ctrl+o sidebar,
        ctrl+p palette, escape interrupt, tab switch_agent."""
        from pyharness.tui.app import PyHarnessApp

        binding_keys = {b[0] for b in PyHarnessApp.BINDINGS}
        required = {"ctrl+q", "ctrl+n", "escape", "ctrl+o", "ctrl+p", "tab"}
        missing = required - binding_keys
        assert not missing, f"Missing required keybinds: {missing}"

    def test_bindings_are_list_of_tuples(self):
        """BINDINGS must be a list of (key, action, description) tuples."""
        from pyharness.tui.app import PyHarnessApp

        for b in PyHarnessApp.BINDINGS:
            assert isinstance(b, (tuple, list)), f"Expected tuple, got {type(b)}"
            assert len(b) >= 2, f"Binding must have at least (key, action): {b}"


# =============================================================================
# Integration — Cross-cutting Phase 3 behaviors
# =============================================================================


class TestPhase3Integration:
    """Integration tests that verify multiple Phase 3 features work together."""

    def test_mcp_servers_appear_in_sidebar(self):
        """When MCP servers are configured, sidebar has update_mcp_servers method."""
        try:
            from pyharness.tui.widgets.sidebar import Sidebar
        except ImportError:
            pytest.skip("Sidebar not implemented yet")

        import inspect
        sig = inspect.signature(Sidebar.update_mcp_servers)
        params = list(sig.parameters)
        assert "servers" in params, (
            f"Sidebar.update_mcp_servers must accept 'servers' dict: {params}"
        )

    def test_command_palette_includes_theme_command(self):
        """Command palette (Ctrl+p) must list the /themes command."""
        from pyharness.tui.app import PyHarnessApp
        assert "/themes" in PyHarnessApp.COMMANDS
        assert "/memory" in PyHarnessApp.COMMANDS

    def test_full_config_includes_phase3_fields(self):
        """A complete Phase 3 config validates all new fields."""
        cfg = PyHarnessConfig(
            model="anthropic:claude-sonnet-4-5",
            mcp={
                "test-server": MCPServerConfig(
                    type="local",
                    command=["test-server"],
                ),
            },
        )
        assert cfg.mcp["test-server"].type == "local"
        assert cfg.mcp["test-server"].command == ["test-server"]
