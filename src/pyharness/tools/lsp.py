"""LSP integration — experimental language server protocol support.

Phase 4: Provides a stub LSP client. Full LSP support (python-lsp-server,
pyright) is deferred to post-v1.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LSPDiagnostic:
    """A diagnostic message from an LSP server."""

    file: str
    line: int
    column: int
    message: str
    severity: str = "info"  # "error", "warning", "info", "hint"


class LSPClient:
    """Stub LSP client — full implementation deferred."""

    def __init__(self) -> None:
        self._servers: dict[str, object] = {}

    def start_server(self, language: str) -> bool:
        """Start an LSP server for a language. Returns True if supported."""
        supported = {"python", "typescript", "rust", "go"}
        return language in supported

    def get_diagnostics(self, file_path: str) -> list[LSPDiagnostic]:
        """Get diagnostics for a file. Returns empty list (stub)."""
        return []

    def get_definition(
        self, file_path: str, line: int, col: int
    ) -> dict | None:
        """Get definition location. Returns None (stub)."""
        return None

    def get_references(self, file_path: str, line: int, col: int) -> list[dict]:
        """Get references. Returns empty list (stub)."""
        return []

    def stop(self) -> None:
        """Stop all LSP servers."""
        self._servers.clear()


# Singleton
_lsp_client: LSPClient | None = None


def get_lsp_client() -> LSPClient:
    """Return the singleton LSP client, creating it if necessary."""
    global _lsp_client
    if _lsp_client is None:
        _lsp_client = LSPClient()
    return _lsp_client
