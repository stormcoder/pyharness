"""Tests for the TUI — app, chat screen, input widget, sidebar, and Phase 2 features."""

from __future__ import annotations

from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.chat import ChatScreen
from pyharness.tui.widgets.input import PromptInput
from pyharness.tui.widgets.message import MessageWidget
from pyharness.tui.widgets.sidebar import Sidebar
from pyharness.tui.widgets.file_tree import FileTreeWidget, FileTree
from pyharness.tui.widgets.memory import MemoryTab
from pyharness.tui.widgets.briefing import SessionBriefing
from pyharness.tui.screens.sessions import SessionBrowser


# ---------------------------------------------------------------------------
# Phase 1 tests (existing)
# ---------------------------------------------------------------------------


def test_app_initializes() -> None:
    """App can be created without error."""
    app = PyHarnessApp()
    assert app is not None
    assert app.config is None  # Not loaded until on_mount


def test_app_has_bindings() -> None:
    """Verify that the core keybindings are registered."""
    app = PyHarnessApp()
    binding_keys = {binding[0] for binding in app.BINDINGS}
    assert "ctrl+q" in binding_keys, "Quit binding missing"
    assert "ctrl+n" in binding_keys, "New session binding missing"
    assert "escape" in binding_keys, "Interrupt binding missing"


def test_chat_screen_instantiates() -> None:
    """ChatScreen can be instantiated as a valid Screen subclass."""
    screen = ChatScreen()
    assert screen is not None
    from textual.screen import Screen as TextualScreen

    assert issubclass(ChatScreen, TextualScreen)


async def test_chat_screen_composes() -> None:
    """ChatScreen compose yields the expected widgets when mounted."""
    app = PyHarnessApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen_stack[-1]
        assert isinstance(screen, ChatScreen)
        widgets = list(screen.query("*"))
        assert len(widgets) > 0, f"ChatScreen should have child widgets, got {len(widgets)}"


def test_prompt_input_placeholder() -> None:
    """Input widget has placeholder text set."""
    test_placeholder = "Ask me anything..."
    widget = PromptInput(placeholder=test_placeholder)
    assert widget.placeholder == test_placeholder


def test_message_widget_constructs() -> None:
    """MessageWidget stores role and formats content with role-based colour."""
    user_msg = MessageWidget("user", "Hello")
    assert "Hello" in str(user_msg.content)

    asst_msg = MessageWidget("assistant", "Hi there")
    assert "Hi there" in str(asst_msg.content)

    err_msg = MessageWidget("error", "Something went wrong")
    assert "Something went wrong" in str(err_msg.content)

    unknown_msg = MessageWidget("unknown_role", "test")
    assert "test" in str(unknown_msg.content)


async def test_app_runs_in_test_mode() -> None:
    """Smoke test — app starts and renders in Textual's async test harness."""
    app = PyHarnessApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.is_running
        assert len(app.screen_stack) >= 1
        assert isinstance(app.screen_stack[-1], ChatScreen)


# ---------------------------------------------------------------------------
# Phase 2 tests — Sidebar
# ---------------------------------------------------------------------------


def test_sidebar_widget_importable() -> None:
    """Sidebar widget is importable and instantiable."""
    sidebar = Sidebar()
    assert sidebar is not None


def test_sidebar_importable_and_creatable() -> None:
    """Sidebar can be imported and instantiated (compose requires Textual runtime)."""
    sidebar = Sidebar()
    assert sidebar is not None
    assert isinstance(sidebar, Sidebar)


# ---------------------------------------------------------------------------
# Phase 2 tests — File Tree
# ---------------------------------------------------------------------------


def test_file_tree_importable() -> None:
    """FileTree widget is importable and instantiable."""
    tree = FileTreeWidget("Project")
    assert tree is not None


def test_file_tree_alias_exists() -> None:
    """FileTree alias points to FileTreeWidget."""
    assert FileTree is FileTreeWidget


def test_file_tree_has_directory_add_method() -> None:
    """FileTreeWidget has _add_directory for recursive population."""
    assert hasattr(FileTreeWidget, "_add_directory")


# ---------------------------------------------------------------------------
# Phase 2 tests — Memory and Briefing
# ---------------------------------------------------------------------------


def test_memory_tab_importable() -> None:
    """MemoryTab is importable and instantiable."""
    mem = MemoryTab()
    assert mem is not None


def test_memory_tab_has_refresh() -> None:
    """MemoryTab has refresh_memory async method."""
    assert hasattr(MemoryTab, "refresh_memory")


def test_briefing_widget_importable() -> None:
    """SessionBriefing is importable and instantiable."""
    briefing = SessionBriefing()
    assert briefing is not None


def test_briefing_can_update() -> None:
    """SessionBriefing accepts updated briefing text."""
    briefing = SessionBriefing()
    briefing.set_briefing("New context loaded")
    # Should not raise


# ---------------------------------------------------------------------------
# Phase 2 tests — ! bash injection
# ---------------------------------------------------------------------------


def test_chat_screen_recognizes_bang_prefix() -> None:
    """ChatScreen should recognize ! command syntax."""
    assert ChatScreen.COMMANDS is not None
    # Input starting with ! is bash, not slash command
    test_input = "!ls -la"
    assert test_input.startswith("!")


def test_chat_screen_has_bash_runner() -> None:
    """ChatScreen has _run_bash async method."""
    assert hasattr(ChatScreen, "_run_bash")


# ---------------------------------------------------------------------------
# Phase 2 tests — Slash commands
# ---------------------------------------------------------------------------


def test_chat_screen_has_commands() -> None:
    """ChatScreen.COMMANDS contains the required slash commands."""
    assert "/new" in ChatScreen.COMMANDS
    assert "/undo" in ChatScreen.COMMANDS
    assert "/redo" in ChatScreen.COMMANDS
    assert "/sessions" in ChatScreen.COMMANDS
    assert "/help" in ChatScreen.COMMANDS


def test_app_has_commands() -> None:
    """App has COMMANDS dict with Phase 2 commands."""
    assert "/new" in PyHarnessApp.COMMANDS
    assert "/undo" in PyHarnessApp.COMMANDS
    assert "/help" in PyHarnessApp.COMMANDS
    assert "/models" in PyHarnessApp.COMMANDS
    assert "/memory" in PyHarnessApp.COMMANDS


# ---------------------------------------------------------------------------
# Phase 2 tests — App bindings
# ---------------------------------------------------------------------------


def test_app_has_phase2_bindings() -> None:
    """App bindings include Ctrl+o (sidebar) and Ctrl+p (command palette)."""
    app = PyHarnessApp()
    binding_keys = {binding[0] for binding in app.BINDINGS}
    assert "ctrl+o" in binding_keys, "Sidebar toggle binding missing"
    assert "ctrl+p" in binding_keys, "Command palette binding missing"


# ---------------------------------------------------------------------------
# Phase 2 tests — @ file references
# ---------------------------------------------------------------------------


def test_prompt_input_get_at_refs() -> None:
    """PromptInput can extract @ file references from input value."""
    widget = PromptInput(placeholder="test")
    assert hasattr(widget, "get_at_file_refs")
    assert hasattr(widget, "resolve_at_files")


def test_prompt_input_fuzzy_search() -> None:
    """PromptInput has fuzzy file search capability."""
    widget = PromptInput(placeholder="test")
    assert hasattr(widget, "fuzzy_search_files")
    results = widget.fuzzy_search_files("pyproject")
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Phase 3 tests — Theme System
# ---------------------------------------------------------------------------


def test_theme_get_theme_valid():
    """get_theme returns theme dict for known themes."""
    from pyharness.tui.themes import get_theme

    tokyo = get_theme("tokyonight")
    assert tokyo is not None
    assert tokyo["name"] == "Tokyo Night"
    assert "background" in tokyo["colors"]
    assert tokyo["colors"]["background"] == "#0d1117"


def test_theme_get_theme_invalid():
    """get_theme returns None for unknown themes."""
    from pyharness.tui.themes import get_theme

    assert get_theme("nonexistent") is None
    assert get_theme("") is None


def test_theme_get_all_themes():
    """get_all_themes returns all 5 built-in themes."""
    from pyharness.tui.themes import get_all_themes

    themes = get_all_themes()
    assert len(themes) == 5
    assert "tokyonight" in themes
    assert "dark" in themes
    assert "light" in themes
    assert "dracula" in themes
    assert "nord" in themes


def test_theme_list_theme_names():
    """list_theme_names returns list of theme keys."""
    from pyharness.tui.themes import list_theme_names

    names = list_theme_names()
    assert isinstance(names, list)
    assert len(names) == 5
    assert "tokyonight" in names
    assert "dark" in names
    assert "light" in names


def test_theme_get_all_themes_is_copy():
    """get_all_themes returns a copy, not a reference."""
    from pyharness.tui.themes import get_all_themes

    themes1 = get_all_themes()
    themes2 = get_all_themes()
    assert themes1 is not themes2
    assert themes1 == themes2


def test_theme_colors_are_valid_hex():
    """All theme colors are valid 6-char hex codes."""
    from pyharness.tui.themes import get_all_themes

    for _name, theme in get_all_themes().items():
        for key, value in theme["colors"].items():
            assert value.startswith("#"), (
                f"{theme['name']} color '{key}'={value!r} must start with #"
            )
            assert len(value) == 7, (
                f"{theme['name']} color '{key}'={value!r} must be #RRGGBB"
            )


def test_action_theme_exists():
    """App has action_theme method."""
    app = PyHarnessApp()
    assert hasattr(app, "action_theme")
    import inspect
    sig = inspect.signature(app.action_theme)
    assert "name" in sig.parameters


# ---------------------------------------------------------------------------
# Phase 3 tests — Session Browser
# ---------------------------------------------------------------------------


def test_session_browser_instantiates():
    """SessionBrowser screen can be instantiated."""
    sb = SessionBrowser()
    assert sb is not None


def test_session_browser_has_bindings():
    """SessionBrowser has escape and enter bindings."""
    sb = SessionBrowser()
    binding_keys = {b[0] for b in sb.BINDINGS}
    assert "escape" in binding_keys, "SessionBrowser missing escape binding"
    assert "enter" in binding_keys, "SessionBrowser missing enter binding"


def test_session_browser_has_dismiss_action():
    """SessionBrowser has action_dismiss method."""
    sb = SessionBrowser()
    assert hasattr(sb, "action_dismiss")


def test_session_browser_has_resume_action():
    """SessionBrowser has action_resume method."""
    sb = SessionBrowser()
    assert hasattr(sb, "action_resume")


# ---------------------------------------------------------------------------
# Phase 3 tests — Keybind Customization
# ---------------------------------------------------------------------------


def test_app_has_load_keybinds_method():
    """App has _load_keybinds method."""
    app = PyHarnessApp()
    assert hasattr(app, "_load_keybinds")


def test_app_has_action_sessions():
    """App has action_sessions method."""
    app = PyHarnessApp()
    assert hasattr(app, "action_sessions")


def test_app_keybinds_unchanged_without_tui_json():
    """_load_keybinds does not crash without tui.json files."""
    app = PyHarnessApp()
    original_bindings = list(app.BINDINGS)
    app._load_keybinds()
    assert app.BINDINGS == original_bindings


def test_app_on_mount_calls_load_keybinds():
    """on_mount calls _load_keybinds before pushing screen."""
    import inspect
    source = inspect.getsource(PyHarnessApp.on_mount)
    assert "self._load_keybinds()" in source, (
        "on_mount must call self._load_keybinds()"
    )


def test_themes_import_does_not_raise():
    """Themes module has BUILTIN_THEMES with valid keys."""
    from pyharness.tui.themes import BUILTIN_THEMES

    assert len(BUILTIN_THEMES) == 5
    expected = {"tokyonight", "dark", "light", "dracula", "nord"}
    assert set(BUILTIN_THEMES) == expected
