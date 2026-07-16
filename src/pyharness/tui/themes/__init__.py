"""Theme system — register and apply Textual CSS themes."""

BUILTIN_THEMES: dict[str, dict] = {
    "tokyonight": {
        "name": "Tokyo Night",
        "description": "Dark theme with blue/purple accents",
        "colors": {
            "background": "#0d1117",
            "surface": "#161b22",
            "primary": "#58a6ff",
            "secondary": "#d2a8ff",
            "success": "#3fb950",
            "warning": "#d29922",
            "error": "#f85149",
            "text": "#c9d1d9",
            "text-muted": "#8b949e",
            "border": "#30363d",
        }
    },
    "dark": {
        "name": "Dark",
        "description": "Minimal dark theme",
        "colors": {
            "background": "#1e1e1e",
            "surface": "#2d2d2d",
            "primary": "#569cd6",
            "secondary": "#c586c0",
            "success": "#4ec9b0",
            "warning": "#ce9178",
            "error": "#f44747",
            "text": "#d4d4d4",
            "text-muted": "#808080",
            "border": "#404040",
        }
    },
    "light": {
        "name": "Light",
        "description": "Clean light theme",
        "colors": {
            "background": "#ffffff",
            "surface": "#f6f8fa",
            "primary": "#0969da",
            "secondary": "#8250df",
            "success": "#1a7f37",
            "warning": "#9a6700",
            "error": "#cf222e",
            "text": "#1f2328",
            "text-muted": "#656d76",
            "border": "#d0d7de",
        }
    },
    "dracula": {
        "name": "Dracula",
        "description": "Classic Dracula color scheme",
        "colors": {
            "background": "#282a36",
            "surface": "#44475a",
            "primary": "#bd93f9",
            "secondary": "#ff79c6",
            "success": "#50fa7b",
            "warning": "#ffb86c",
            "error": "#ff5555",
            "text": "#f8f8f2",
            "text-muted": "#6272a4",
            "border": "#6272a4",
        }
    },
    "nord": {
        "name": "Nord",
        "description": "Arctic, north-bluish color palette",
        "colors": {
            "background": "#2e3440",
            "surface": "#3b4252",
            "primary": "#88c0d0",
            "secondary": "#b48ead",
            "success": "#a3be8c",
            "warning": "#ebcb8b",
            "error": "#bf616a",
            "text": "#eceff4",
            "text-muted": "#4c566a",
            "border": "#434c5e",
        }
    },
}


def get_theme(name: str) -> dict | None:
    """Return a theme definition by name, or None if not found."""
    return BUILTIN_THEMES.get(name)


def get_all_themes() -> dict[str, dict]:
    """Return a copy of all registered themes."""
    return dict(BUILTIN_THEMES)


def list_theme_names() -> list[str]:
    """Return a list of all registered theme names."""
    return list(BUILTIN_THEMES.keys())
