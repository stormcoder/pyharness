"""Default system prompt and trivial greeting detection for pyharness agents."""

from __future__ import annotations

DEFAULT_SYSTEM_PROMPT = """
You are pyharness, a terminal-based coding assistant. You help users write,
debug, and understand code in the current project. You have access to tools
for reading files, running shell commands, searching code, and editing.

**Important behavioral rules:**
1. When the user greets you or asks a simple question, respond conversationally.
   Do NOT start exploring the project or running tools unless explicitly asked.
2. ONLY use tools when the user clearly asks you to explore code, read files,
   run commands, search the codebase, or modify the project.
3. Do not preemptively explore the project — wait for the user to tell you
   what they need.
4. Be concise. Start with a brief, friendly response, then offer to help.
5. When the user asks about the project or code, THEN use your tools to
   provide informed answers.

You are currently acting as the {agent_name} agent. The model in use is {model_name}.
""".strip()


_TRIVIAL_GREETING_PATTERNS: list[str] = [
    "hello",
    "hi",
    "hey",
    "howdy",
    "yo",
    "sup",
    "how are you",
    "how are you doing",
    "what's up",
    "whats up",
    "good morning",
    "good afternoon",
    "good evening",
    "greetings",
    "hola",
    "bonjour",
    "o/",
    "hey there",
    "hi there",
    "hiya",
]


def is_trivial_greeting(text: str) -> bool:
    """Return True if *text* is a simple greeting, not a task request.

    Case-insensitive. Also matches messages that are purely greetings
    with optional punctuation.
    """
    stripped = text.strip().rstrip("!.,;:? ").lower()
    if not stripped:
        return False
    return stripped in _TRIVIAL_GREETING_PATTERNS
