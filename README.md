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
python3.12 -m venv .venv && source .venv/bin/activate   # needs Python >= 3.12
pip install -e .               # core: chat, plan, run, ingest, ask, memory
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
manas browse https://url       # page -> readable text
# the next three need: pip install -e ".[perception]"  (+ brew/apt tesseract-ocr)
manas ocr screenshot.png       # screen understanding (Tesseract)
manas agenda                   # local-first calendar (.ics)
manas calendar-add "standup" 2026-07-29T10:00:00+05:30
# screenshots / live browser / voice: pip install -e ".[perception-full]"
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

### Shipped — v1.0.0

| Phase | Delivers                                                                | Ver.   | Verified by |
|-------|-------------------------------------------------------------------------|--------|-------------|
| 0     | Recon protocol + hierarchical prompt system (`prompts/00..60`)          | 0.1.0  | all agents load layers |
| 1     | Kernel: registry, event bus, config, audit, ToolGate, memory, CLI, API  | 0.1.0  | gate blocks unapproved shell; audit trail |
| 2     | SQLite + embeddings memory (versioned, archival), curator agent         | 0.2.0  | JSONL auto-migration; decay/promote tests |
| 3     | Orchestrator + critic loop; task DAGs; resumable plans                  | 0.3.0  | crash-resume with context injection |
| 4     | Knowledge engine: repo/PDF/ticket ingestion → knowledge tier            | 0.4.0  | dogfood: MANAS ingested itself (RAG) |
| 5     | Integrations: GitHub/GHE, Jira, TestRail, Slack, email via ToolGate     | 0.5.0  | live GitHub sync; mock contract tests |
| 6     | Perception: OCR, voice pipeline, browser, local-first ICS calendar      | 0.6.0  | real Tesseract OCR; tz-instant regression |
| 7     | Observability: Prometheus metrics, span tracing, deep health checks     | 0.7.0  | live /metrics scrape; task→LLM span trees |
| 8     | Self-improvement: reflection deltas → episodic lessons → future plans   | 1.0.0  | lessons retrieved into next plan |

41 tests. Ship rule held throughout: every phase left `pytest` green and the CLI usable.

### Shipped — second horizon (v1.6.0)

| Phase | Delivers                                                                 | Ver.   | Acceptance proven by |
|-------|--------------------------------------------------------------------------|--------|----------------------|
| 9     | Provider hardening: retry/backoff, fallback chain, purpose routing, token+cost metrics, streaming | 1.1.0 | flaky provider degraded to fallback after 3 retries; cost counter scrapeable |
| 10    | Computer control: gated keyboard/mouse/app tools with mandatory dry-run  | 1.2.0  | live run refused until the exact sequence was previewed |
| 11    | RBAC ceilings + split Fernet-encrypted personal/enterprise stores        | 1.3.0  | plaintext absent from db bytes; cross-store recall denied w/o explicit grant |
| 12    | Distributed execution: lease table, DistWorker nodes, k8s manifests      | 1.4.0  | two nodes shared one graph; expired lease reclaimed after node death |
| 13    | Continuous ingestion: watch registry + polling re-ingest                 | 1.5.0  | edited file re-ingested automatically, stale chunks archived |
| 14    | Edge/robotics: MQTT sensors (SAFE) + actuators (hard always_gate)        | 1.6.0  | actuation impossible without a human approver callable, per invocation |

60 tests. Ship rule held: every phase left `pytest` green and the CLI usable.

### Beyond (unscheduled)

Live CalDAV + mail watchers · OpenTelemetry export of traces · vector-index
acceleration (FAISS/sqlite-vec) at corpus scale · AR/voice always-on frontends
· multi-tenant API auth. Each enters the roadmap only with a testable
"ships working when…" criterion, per the operating contract.

## Non-negotiables (from `prompts/00_core_identity.md`)

Human approval gates never come off. Secrets never appear in logs or output.
Every change leaves MANAS working. Everything is a replaceable module.
