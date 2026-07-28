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

## 1.1.0 → 1.6.0 — second horizon (phases 9–14)
- 1.1.0 P9  providers: retry/backoff, fallback chain, purpose routing,
             token+cost counters, streaming interface
- 1.2.0 P10 desktop control: APPROVAL tools, dry-run-first replay rule,
             text never echoed into plans/audit
- 1.3.0 P11 RBAC role ceilings enforced in ToolGate; personal/enterprise
             stores split + Fernet-encrypted at rest; explicit-grant
             cross-store recall
- 1.4.0 P12 distributed workers over a SQLite lease table with node-death
             recovery; k8s manifests (API + scaled workers on RWX PVC)
- 1.5.0 P13 persistent watch registry + polling re-ingest with stale archival
- 1.6.0 P14 MQTT sensor/actuator tools; always_gate hard rule in the kernel;
             ToolGate hardened to read risk metadata from instances
