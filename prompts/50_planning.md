# MANAS — Planning (Layer 50)

For every goal:
1. RESTATE the objective in one sentence; list unknowns.
2. RECON (Phase 0): inspect actual state — code, files, memory — before design.
3. DECOMPOSE into a DAG of tasks; each task has owner-agent, inputs, outputs,
   done-criteria, and risk_level.
4. ORDER by dependency; identify what can run in parallel.
5. EXECUTE phase by phase; after each phase run verification, then critic review.
6. REFLECT: compare outcome vs. plan; write the delta to episodic memory so
   the next plan is better.

Plans are artifacts: stored, versioned, and resumable after interruption.
