# MANAS — Coding Standards (Layer 20)

- Language baseline: Python 3.12+, full type hints, `from __future__` not needed.
- Architecture: clean/hexagonal. Domain logic never imports FastAPI, Typer,
  or any provider SDK. Adapters live at the edges.
- Every module: docstring stating purpose + its layer in the OS.
- Errors: raise typed exceptions from `manas.kernel.errors`; never bare except.
- Logging: structured (key=value), via `manas.kernel.log`. No print() in library code.
- Config: pydantic-settings, env-driven, `.env` never committed. Every setting
  has a safe default that works offline.
- Tests: unit tests for kernel logic, contract tests for every provider,
  smoke test for the CLI. A feature without tests is not done.
- Async by default at the I/O boundary; pure sync for pure logic.
- Dependencies: minimal, pinned in pyproject, each one justified in a comment.
- Providers, tools, memories, agents are all registered via the same
  registry pattern — adding one must never require editing kernel code.
