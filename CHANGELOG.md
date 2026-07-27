# MANAS Changelog

## 1.0.0 — all eight roadmap phases complete
- P0/P1 Kernel: registry, event bus, config, scrubbed logging, audit,
  ToolGate (denylist/jail/approval), tiered memory, CLI + FastAPI,
  hierarchical prompt system (prompts/00..60)
- P2 Memory: SQLite + embeddings backend (versioned, archival, access-scored
  recall), offline hash embedder, auto-migration from JSONL, curator agent
- P3 Orchestration: task DAG (validated, persisted, resumable), orchestrator
  with capped changed-strategy retries, critic review loop
- P4 Knowledge: repo/doc/PDF/ticket ingestion, idempotent content-hash
  chunking, stale-chunk archival, researcher agent (RAG with sources)
- P5 Integrations: GitHub/GHE, Jira, TestRail, Slack, email through the
  ToolGate (reads SAFE, writes APPROVAL), sync-to-knowledge bridge
- P6 Perception: Tesseract OCR, voice pipeline (pluggable STT/TTS, wake-word
  logic), browser fetch + gated Playwright actions, local-first ICS calendar
- P7 Observability: Prometheus-format metrics, nested span tracing,
  deep health checks (doctor, /healthz, /metrics, /traces)
- P8 Learning: post-run reflection deltas -> episodic lessons -> injected
  into future plans; failures weighted above successes
