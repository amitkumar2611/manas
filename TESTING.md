# Testing MANAS

Two different things are called "testing" here, and they prove different things:

| | Proves | Needs |
|---|---|---|
| **Offline suite** (`pytest`) | The kernel's logic is correct | Nothing — no keys, no network |
| **Live-system testing** | It behaves safely against real LLMs, real systems, real data | Credentials, and care |

The offline suite runs entirely on the `echo` stub provider and mocked transports.
It can be green while the system is still untested against anything real — so do
both, in that order.

---

## 1. Environment setup

MANAS needs **Python 3.12+**. On macOS the system `python3` is often 3.11, which
is below the floor; use an explicit interpreter.

```bash
python3.12 -m venv ~/.venvs/manas          # keep the venv OUT of any synced folder
~/.venvs/manas/bin/pip install -e ".[perception]"
```

| Install | Gets you |
|---------|----------|
| `pip install -e .` | Core: `chat`, `plan`, `run`, `ingest`, `ask`, memory, integrations, API |
| `pip install -e ".[perception]"` | Adds OCR + local `.ics` calendar |
| `pip install -e ".[perception-full]"` | Adds screenshots, live browser (Playwright), voice |

Some capabilities also need a **system binary**, not just a Python package:

| Capability | Extra install |
|------------|---------------|
| `manas ocr` | `brew install tesseract` (or `apt install tesseract-ocr`) |
| `browser_act` | `playwright install chromium` |
| `desktop_control` | `pip install pyautogui` + a real display |
| IoT `sensor_read` / `actuate` | `pip install paho-mqtt` + a reachable MQTT broker |

Each of these fails with a `ManasError` naming exactly what to install — it never
returns a fake result.

### Putting `manas` on your PATH

An editable install exposes the entry point inside the venv. To call it from
anywhere without activating:

```bash
ln -sf ~/.venvs/manas/bin/manas ~/.local/bin/manas   # ~/.local/bin must be on PATH
manas status
```

`zsh: command not found: manas` means only that this step was skipped — the
package is installed in a venv you haven't activated.

---

## 2. The offline test suite

```bash
python -m pytest tests/ -q
```

**Expected: 60 passed.** Any failure is a real regression, with one exception:

```
test_ocr_reads_real_image ... TesseractNotFoundError
```

That means the `pytesseract` Python package is present but the **Tesseract binary**
is not. Either `brew install tesseract`, or skip it:

```bash
python -m pytest tests/ -q --deselect tests/test_kernel.py::test_ocr_reads_real_image
```

The suite covers all fourteen phases: registry and permissions, gate denial,
memory versioning and migration, DAG cycle detection and crash-resume, knowledge
ingest/dedup/staleness, integrations (mocked `httpx` — no live credentials),
perception, metrics and tracing, the reflection loop, provider fallback, RBAC
ceilings, encrypted scoped stores, lease-based distributed execution, and IoT
gating.

### Keep test state out of your real home

Everything MANAS writes goes under `MANAS_HOME` (default `~/.manas`). Point it
somewhere disposable while testing:

```bash
export MANAS_HOME=/tmp/manas-test
```

---

## 3. Testing on a live system

Work these stages **in order**. Each proves a layer before you trust the next.

### Stage 0 — Baseline, no credentials

```bash
export MANAS_HOME=~/.manas-live
manas doctor                      # must exit 0
manas status
manas run "audit the repo docs"
```

`doctor` runs six checks: `prompts`, `memory`, `audit`, `provider`, `disk`,
`registries`. If it isn't green, stop — nothing downstream is trustworthy.

### Stage 1 — Real inference

`echo` is a stub. Nothing above it is genuinely exercised until you swap it.

```bash
# Local — no keys, no data leaves the machine (start here)
ollama serve &
ollama pull llama3.1
export MANAS_PROVIDER=ollama MANAS_EMBEDDER=ollama

# Or cloud
export MANAS_PROVIDER=anthropic MANAS_ANTHROPIC_API_KEY=sk-...
```

```bash
manas chat
manas plan "add rate limiting to the API"
```

**Switch `MANAS_EMBEDDER` off `hash`.** The default is a deterministic offline
stand-in, not a real embedding model — retrieval quality is meaningless until you
move to `ollama`. This is the single most common reason live RAG results look
worse than expected.

Then exercise the phase-9 provider hardening:

```bash
export MANAS_PROVIDER_FALLBACKS="ollama,echo"   # kill ollama mid-run; must fail over
export MANAS_ROUTES="critic=ollama:llama3.1"    # per-agent model routing
export MANAS_COST_PER_MTOK="anthropic=3:15"     # cost accounting
manas metrics | grep -E 'llm_requests|cost'
```

### Stage 2 — Knowledge on real data

```bash
manas ingest ~/code/some-repo
manas ingest ~/code/some-repo      # MUST report chunks_new=0
manas ask "how does auth work here?"
```

The second ingest is the real test. Reporting new chunks on unchanged input means
content-hash dedup is broken. Edit a file and re-ingest: stale chunks should be
archived, not deleted.

### Stage 3 — Integrations, reads first

```bash
export MANAS_GITHUB_TOKEN=ghp_...
manas sync github owner/repo

export MANAS_JIRA_URL=https://jira.example.com
export MANAS_JIRA_EMAIL=you@example.com MANAS_JIRA_TOKEN=...
manas sync jira PROJ-1234
```

For GitHub Enterprise: `export MANAS_GITHUB_API=https://github.hpe.com/api/v3`.

Both syncs are idempotent — a second run should report `0` new records.

### Stage 4 — Prove the approval gate (do not skip)

This is the stage that matters on a live system. Before pointing MANAS at
anything that can write to production:

```bash
export MANAS_APPROVAL_MODE=deny        # hard-refuse instead of prompting
manas run "post a status summary to slack"   # must refuse, not post
tail -5 $MANAS_HOME/audit.jsonl              # refusals must be recorded
```

There is deliberately **no `auto` approval mode** — only `ask` and `deny`.

Confirm the audit trail records refusals *before* trusting any write path. Skip
this and the first thing you'll test is whether it can post to your team's Slack.

### Stage 5 — Observability

```bash
uvicorn manas.api:app --port 8420
```

| Route | Use |
|-------|-----|
| `/healthz` | Readiness probe — the six `doctor` checks as JSON |
| `/health` | Liveness |
| `/metrics` | Prometheus scrape target |
| `/traces` | Recent span trees |
| `/chat` | Kernel over HTTP |

```bash
manas traces --n 3     # agent -> tool -> LLM span nesting
```

### Stage 6 — Second-horizon capabilities

```bash
manas watch ~/code/some-repo --once          # continuous re-ingest, one cycle
manas watch ~/code/some-repo --interval 30   # daemon

manas worker --all --node-id node-1          # distributed execution
```

For `worker`, run two nodes against a shared `MANAS_HOME` and **kill one
mid-graph**. Surviving nodes must reclaim the lease and finish the work. That
node-death path is the part worth testing before relying on it.

### Stage 7 — Run it as a service

See [DEPLOY.md](DEPLOY.md) for Docker, `docker compose` (bundles Ollama for a
zero-cloud stack), systemd via `deploy/manas.service`, and Kubernetes via
`deploy/k8s.yaml`.

---

## 4. Tool risk reference

The ToolGate classifies every tool. Order of enforcement: **denylist → jail →
approval → audit**.

| Risk | Behaviour | Tools |
|------|-----------|-------|
| `SAFE` | Runs freely | `read_file`, `github_fetch`, `jira_fetch`, `testrail_fetch`, `browser_fetch`, `ocr_image`, `screenshot`, `transcribe`, `calendar_read`, `sensor_read` |
| `REVIEW` | Logged, elevated | `write_file`, `calendar_add` |
| `APPROVAL` | Blocked without a human approver | `shell`, `slack_post`, `email_send`, `jira_comment`, `testrail_add_result`, `browser_act`, `desktop_control`, `actuate` |

`actuate` (IoT) additionally carries `always_gate = True`: the gate refuses even
to consult an approver when none is wired, and rejects wildcard topics outright.

A hard denylist (`rm -rf /`, `mkfs`, `curl | sh`, …) is checked before anything
else and is not approvable.

---

## 5. Environment variables

All are prefixed `MANAS_`. Copy `.env.template` to `.env` — every default works
offline.

| Variable | Default | Notes |
|----------|---------|-------|
| `HOME` | `~/.manas` | All state: memory, audit, plans, keys |
| `PROVIDER` | `echo` | `echo` / `anthropic` / `copilot` / `ollama` |
| `MODEL` | *(blank)* | Provider-specific id |
| `EMBEDDER` | `hash` | `hash` (offline stub) / `ollama` (real) |
| `MEMORY_BACKEND` | `sqlite` | `sqlite` / `jsonl` (legacy) |
| `APPROVAL_MODE` | `ask` | `ask` / `deny` — never `auto` |
| `WORKDIR_JAIL` | cwd | Filesystem jail for file tools |
| `PROVIDER_FALLBACKS` | *(blank)* | e.g. `ollama,echo` |
| `ROUTES` | *(blank)* | e.g. `critic=ollama:llama3.1` |
| `PERSONAL_KEY` / `ENTERPRISE_KEY` | *(autogen)* | Fernet keys → `~/.manas/keys/` (0600) |
| `MQTT_BROKER` | `localhost:1883` | IoT broker |

Credentials: `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `GITHUB_API`, `JIRA_URL`,
`JIRA_EMAIL`, `JIRA_TOKEN`, `TESTRAIL_*`, `SLACK_WEBHOOK`, `SMTP_*`.

---

## 6. Troubleshooting

**`zsh: command not found: manas`**
The venv isn't on your PATH. Symlink the entry point (§1) or activate the venv.

**`ModuleNotFoundError` on `import manas`**
An optional backend is being imported eagerly. Optional deps must be imported
*inside* the tool that uses them, raising `ManasError` with the install hint —
see `manas/perception/screen.py` for the correct pattern.

**`TesseractNotFoundError`**
The Python package is installed but the system binary isn't. `brew install tesseract`.

**Retrieval returns weak matches**
You're still on the `hash` embedder. Set `MANAS_EMBEDDER=ollama`.

**Rich `MarkupError`, or labels missing from output**
Dynamic text is being parsed as console markup. Untrusted text must go through
`rich.markup.escape`, and literal brackets must be written `\[`.

**A tool silently does nothing**
Check `$MANAS_HOME/audit.jsonl` — it was probably refused by the gate.

---

## 7. Known gaps

- `pyproject.toml` still declares `version = "0.7.0"` while the CHANGELOG
  documents through 1.6.0. Bump before cutting a release.
- The offline suite mocks every integration transport. Live credential paths
  (Stage 3) are only covered by manual testing.
- `hash` embedder means offline RAG assertions verify plumbing, not retrieval
  quality.
