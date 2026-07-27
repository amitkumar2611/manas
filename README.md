# MANAS

**M**odular **A**utonomous **N**eural **A**gent **S**ystem — an AI Operating System kernel.
*Manas* (Sanskrit: मनस्) — "mind." Not a chatbot. A mind with a permission system.

```
                                MANAS  v0.1.0
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  PRESENTATION            cli.py (typer)      api.py (FastAPI)           │
 │                              │                    │                     │
 ├──────────────────────────────┼────────────────────┼─────────────────────┤
 │  AGENTS                      ▼                    ▼                     │
 │      ┌───────────┐      ┌───────────┐      ┌───────────┐               │
 │      │ assistant │      │  planner  │      │  (yours)  │  ◄─ register  │
 │      └─────┬─────┘      └─────┬─────┘      └───────────┘     & go      │
 │            │   typed events ONLY — no agent imports another agent       │
 │  ┌─────────▼─────────────────▼──────────────────────────────────────┐  │
 │  │                      KERNEL EVENT BUS                            │  │
 │  │   registry ─ events ─ config ─ log(scrubbed) ─ errors ─ audit    │  │
 │  └───────┬──────────────────────┬───────────────────────┬───────────┘  │
 │          │                      │                       │              │
 │  MEMORY  ▼              TOOLS   ▼               PROVIDERS ▼            │
 │  ┌──────────────┐      ┌──────────────┐      ┌──────────────────┐     │
 │  │ tiered store │      │   ToolGate   │      │ complete()       │     │
 │  │ working      │      │  denylist    │      │  ├─ echo (off-   │     │
 │  │ conversation │      │  jail        │      │  │   line dflt)  │     │
 │  │ episodic     │      │  APPROVAL ⛔ │      │  ├─ ollama       │     │
 │  │ semantic     │      │  audit.jsonl │      │  ├─ anthropic    │     │
 │  │ knowledge    │      │              │      │  └─ copilot      │     │
 │  └──────────────┘      └──────┬───────┘      └──────────────────┘     │
 │                               ▼                                        │
 │                    shell · read_file · write_file · (yours)            │
 └─────────────────────────────────────────────────────────────────────────┘
```

## Why this shape

- **One registry pattern for everything.** Agents, tools, providers, memories all
  self-register with a decorator. Adding a capability never touches kernel code.
- **ToolGate is the only door to the real world.** Denylist → jail → approval →
  audit, in that order. There is deliberately no "auto-approve" mode.
- **Hierarchical prompt system** (`prompts/`). Layer 0 (core identity) always
  loads; each agent loads only the layers it needs — smaller context, sharper
  reasoning, per-agent specialization. See `manas/agents/base.py::load_layers`.
- **Local-first, key-optional.** The `echo` provider keeps the entire OS runnable
  with zero credentials; swap to `ollama` / `anthropic` / `copilot` via `.env`.

## Quickstart

```bash
pip install -e .
cp .env.template .env          # optional — defaults work offline

manas status                   # kernel + registered components
manas chat                     # memory-aware conversation
manas plan "add a voice layer" # phased plan (markdown) saved to ~/.manas/plans/
manas run "audit repo docs"    # goal -> task DAG -> execute w/ critic review
manas graphs                   # list saved graphs and completion state
manas resume ~/.manas/plans/graph-<id>.json   # continue an interrupted run
manas ingest ~/code/my-repo    # repo/docs -> knowledge tier (idempotent)
manas ingest tickets.json --tickets           # Jira-shaped ticket JSON
manas ask "how does auth work in this repo?"  # RAG with source attribution
manas sync jira HPCM-1234      # live ticket -> knowledge (needs Jira creds)
manas sync github owner/repo   # repo + open PRs -> knowledge
manas ocr screenshot.png       # screen understanding (Tesseract)
manas browse https://url       # page -> readable text
manas agenda                   # local-first calendar (.ics)
manas calendar-add "standup" 2026-07-29T10:00:00+05:30
# optional heavy backends: pip install "manas[perception-full]"
manas doctor                   # deep health checks, exit 1 on failure
manas traces --n 3             # recent span trees (agent -> tool -> LLM)
# scrape http://host:8420/metrics with Prometheus; /healthz for readiness
manas remember "I prefer dark-themed HTML reports"
manas recall "html reports"

uvicorn manas.api:app --port 8420    # same kernel over HTTP
python -m pytest tests/ -q
```

## The hierarchical prompt system (`prompts/`)

| Layer | File                    | Loaded when                          |
|-------|-------------------------|--------------------------------------|
| 00    | core_identity.md        | always (all agents inherit)          |
| 10    | agent_rules.md          | agent design / orchestration         |
| 20    | coding_standards.md     | code generation & review             |
| 30    | security.md             | tools, secrets, execution            |
| 40    | memory.md               | any memory read/write                |
| 50    | planning.md             | goal decomposition                   |
| 60    | output_contract.md      | design / implementation deliverables |

## Extending (no kernel edits, ever)

```python
# my_tool.py
from manas.kernel.registry import tools

@tools.register("jira_fetch")
class JiraFetch:
    risk_level = "SAFE"                  # SAFE | REVIEW | APPROVAL
    async def __call__(self, ticket: str) -> dict:
        ...
```

```python
# my_agent.py
from manas.agents.base import BaseAgent
from manas.kernel.registry import agents

@agents.register("qa")
class QAAgent(BaseAgent):
    name, purpose = "qa", "generate and verify test coverage"
    prompt_layers = ("20_coding_standards.md", "50_planning.md")
    tool_allowlist = ("jira_fetch", "read_file")
    memory_scopes = ("working", "episodic")
```

## Roadmap (phased — each phase ships working)

| Phase | Delivers                                                                | Status |
|-------|-------------------------------------------------------------------------|--------|
| 0     | Recon protocol + hierarchical prompts                                   | ✅     |
| 1     | Kernel: registry, bus, config, audit, ToolGate, tiered memory, CLI, API | ✅     |
| 2     | SQLite + embeddings memory backend (same interface), curator agent      | ✅     |
| 3     | Orchestrator + critic loop; task DAG execution; resumable plans         | ✅     |
| 4     | Knowledge engine: repo/PDF/ticket ingestion → knowledge tier            | ✅     |
| 5     | Integrations: GitHub/GHE, Jira, TestRail, Slack, email — per-tool risk  | ✅     |
|       | levels through the same ToolGate (calendar deferred to Phase 6)         |        |
| 6     | Perception: OCR/screen, voice pipeline, browser, local-first calendar   | ✅     |
| 7     | Observability: Prometheus metrics, span tracing, deep health checks     | ✅     |
| 8     | Self-improvement loop: reflection deltas feed the planner               | ⬜     |

## Non-negotiables (from `prompts/00_core_identity.md`)

Human approval gates never come off. Secrets never appear in logs or output.
Every change leaves MANAS working. Everything is a replaceable module.
