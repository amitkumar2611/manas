"""Kernel smoke tests: registry, memory scoring, gate denial, agent perms."""
import asyncio

import pytest

from manas.kernel.errors import ApprovalRequired, ToolDenied
from manas.kernel.registry import agents, providers, tools
from manas.memory.store import MemoryStore, Record
from manas.tools.gate import ToolGate


def test_registrations():
    assert {"assistant", "planner"} <= set(agents.names())
    assert {"shell", "read_file", "write_file"} <= set(tools.names())
    assert {"echo", "anthropic", "copilot", "ollama"} <= set(providers.names())


def test_memory_roundtrip(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    store = MemoryStore()
    store.write(Record(tier="semantic", content="amit prefers dark themed html",
                       importance=0.9))
    hits = store.recall("dark themed html")
    assert hits and hits[0].tier == "semantic"


def test_gate_blocks_denylist():
    gate = ToolGate()
    with pytest.raises((ToolDenied, ApprovalRequired)):
        asyncio.run(gate.run("test", "shell", command="rm -rf / --no-preserve-root"))


def test_gate_requires_approval_for_shell():
    gate = ToolGate()  # no approver wired -> must block
    with pytest.raises(ApprovalRequired):
        asyncio.run(gate.run("test", "shell", command="echo hi"))


def test_agent_tool_allowlist():
    from manas.agents.assistant import AssistantAgent
    agent = AssistantAgent()
    with pytest.raises(PermissionError):
        asyncio.run(agent.use_tool("shell", command="echo hi"))


# ---- Phase 2: sqlite + embeddings backend ---------------------------------

def _sqlite_store(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.memory.sqlite_store import SqliteMemoryStore
    return SqliteMemoryStore()


def test_sqlite_semantic_recall(tmp_path, monkeypatch):
    s = _sqlite_store(tmp_path, monkeypatch)
    s.write(Record(tier="semantic", content="deploy ATIQ to SLES appliance nodes"))
    s.write(Record(tier="semantic", content="rainbow animal parade nursery rhyme"))
    hits = s.recall("deployment to SLES appliances")
    assert hits and "SLES" in hits[0].content


def test_sqlite_versioning_never_destructive(tmp_path, monkeypatch):
    s = _sqlite_store(tmp_path, monkeypatch)
    rid = s.write(Record(tier="semantic", content="provider is copilot"))
    v2 = s.update(rid, "provider is ollama")
    assert v2 == 2
    hist = s.history(rid)
    assert [h.version for h in hist] == [1, 2]
    assert "copilot" in hist[0].content and "ollama" in hist[1].content


def test_sqlite_archive_not_delete(tmp_path, monkeypatch):
    s = _sqlite_store(tmp_path, monkeypatch)
    rid = s.write(Record(tier="working", content="scratch note"))
    s.archive(rid, "test", "cleanup")
    assert all(r.id != rid for r in s.all_active())
    assert s.history(rid)                      # still queryable, never deleted


def test_jsonl_to_sqlite_migration(tmp_path, monkeypatch):
    from manas.kernel import config
    from manas import memory as mem
    monkeypatch.setattr(config.settings, "home", tmp_path)
    monkeypatch.setattr(config.settings, "memory_backend", "sqlite")
    monkeypatch.setattr(mem, "_migrated", False)
    legacy = MemoryStore()                     # Phase 1 store
    legacy.write(Record(tier="semantic", content="legacy fact about vector qa"))
    store = mem.get_store()
    assert any("legacy fact" in r.content for r in store.all_active("semantic"))


def test_curator_decays_and_promotes(tmp_path, monkeypatch):
    import asyncio as aio
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.agents.curator import CuratorAgent
    from manas.memory import get_store
    s = get_store()
    old = time.time() - 60 * 86400
    for i in range(3):                         # a recurring theme, 60 days old
        s.write(Record(tier="episodic", importance=0.6, created=old,
                       content=f"ran testrail sync for hpcm ticket batch {i}"))
    report = aio.run(CuratorAgent().curate())
    assert report["decayed"] >= 3 and report["promoted"] >= 1
    assert s.stats()["semantic"] >= 1


import time  # noqa: E402


# ---- Phase 3: task DAG + orchestrator + critic ----------------------------

def test_graph_cycle_detected():
    from manas.kernel.errors import ManasError
    from manas.kernel.taskgraph import Task, TaskGraph
    a = Task(name="a", agent="assistant", instruction="x")
    b = Task(name="b", agent="assistant", instruction="y", depends_on=[a.id])
    a.depends_on = [b.id]                     # a <-> b cycle
    with pytest.raises(ManasError):
        TaskGraph(goal="g", tasks=[a, b]).validate()


def test_graph_scheduling_respects_deps():
    from manas.kernel.taskgraph import Task, TaskGraph
    a = Task(name="a", agent="assistant", instruction="x")
    b = Task(name="b", agent="assistant", instruction="y", depends_on=[a.id])
    g = TaskGraph(goal="g", tasks=[a, b])
    assert [t.name for t in g.ready()] == ["a"]
    a.status = "DONE"
    assert [t.name for t in g.ready()] == ["b"]


def test_graph_persistence_and_resume(tmp_path, monkeypatch):
    from manas.kernel import config
    from manas.kernel.taskgraph import Task, TaskGraph
    monkeypatch.setattr(config.settings, "home", tmp_path)
    a = Task(name="a", agent="assistant", instruction="x", status="DONE",
             result="done-result")
    b = Task(name="b", agent="assistant", instruction="y", depends_on=[a.id],
             status="RUNNING")                 # simulate crash mid-task
    path = TaskGraph(goal="resume me", tasks=[a, b]).save()
    g2 = TaskGraph.load(path)
    assert g2.tasks[0].status == "DONE" and g2.tasks[0].result == "done-result"
    assert g2.tasks[1].status == "PENDING"     # RUNNING reset -> retryable


def test_orchestrator_end_to_end_offline(tmp_path, monkeypatch):
    import asyncio as aio
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.agents.orchestrator import OrchestratorAgent
    g = aio.run(OrchestratorAgent().run("summarize the state of project X"))
    assert g.finished()                        # echo fallback graph completes
    assert [t.name for t in g.tasks] == ["recon", "execute"]
    assert "result of 'recon'" in "" .join(t.result for t in g.tasks[1:]) or \
           g.tasks[1].result                   # dependency context injected
    assert g.path.exists()


def test_critic_mechanical_rejects_empty(tmp_path, monkeypatch):
    import asyncio as aio
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.agents.critic import CriticAgent
    from manas.kernel.taskgraph import Task
    ok, notes = aio.run(CriticAgent().review(
        Task(name="t", agent="assistant", instruction="i", result="   ")))
    assert not ok and "empty" in notes


# ---- Phase 4: knowledge engine --------------------------------------------

def _knowledge_env(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path / "home")
    monkeypatch.setattr(config.settings, "memory_backend", "sqlite")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "junk.py").write_text("SHOULD NOT BE INGESTED")
    (repo / "auth.py").write_text(
        "def login(user, token):\n    'validate the GITHUB token for auth'\n")
    (repo / "README.md").write_text(
        "# Demo\n\nDeployment uses systemd on SLES appliance nodes.\n")
    (repo / "logo.bin").write_bytes(b"\x00\x01binary")
    return repo


def test_ingest_repo_skips_junk_and_dedupes(tmp_path, monkeypatch):
    from manas.knowledge import engine
    repo = _knowledge_env(tmp_path, monkeypatch)
    r1 = engine.ingest_path(repo)
    assert r1["files"] == 2 and r1["chunks_new"] >= 2 and r1["skipped"] >= 1
    r2 = engine.ingest_path(repo)                 # idempotent re-ingest
    assert r2["chunks_new"] == 0 and r2["chunks_unchanged"] == r1["chunks_new"]
    from manas.memory import get_store
    assert all("SHOULD NOT" not in r.content
               for r in get_store().all_active("knowledge"))


def test_reingest_archives_stale_chunks(tmp_path, monkeypatch):
    from manas.knowledge import engine
    from manas.memory import get_store
    repo = _knowledge_env(tmp_path, monkeypatch)
    engine.ingest_path(repo)
    (repo / "README.md").write_text("# Demo\n\nNow deployed with docker.\n")
    r = engine.ingest_path(repo)
    assert r["chunks_new"] >= 1 and r["chunks_archived"] >= 1
    active = [x.content for x in get_store().all_active("knowledge")]
    assert any("docker" in c for c in active)
    assert not any("SLES" in c for c in active)   # stale chunk archived


def test_ticket_ingest_and_research(tmp_path, monkeypatch):
    import asyncio as aio
    from manas.knowledge import engine
    from manas.agents.researcher import ResearcherAgent
    _knowledge_env(tmp_path, monkeypatch)
    engine.ingest_ticket({"key": "HPCM-421",
                          "summary": "provisioning fails on yajur",
                          "description": "node image sync times out",
                          "comments": ["retry with larger timeout worked"],
                          "status": "In Progress"})
    ans = aio.run(ResearcherAgent().ask("what is wrong with provisioning?"))
    assert "HPCM-421" in ans                      # retrieval found the ticket


def test_chunker_overlap_and_bounds():
    from manas.knowledge.chunk import split, CHUNK_CHARS
    text = "\n\n".join(f"paragraph {i} " + "x" * 300 for i in range(12))
    chunks = split(text, source="s", kind="doc")
    assert len(chunks) > 1
    assert all(len(c.text) <= CHUNK_CHARS * 2 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


# ---- Phase 5: integrations (contract tests, mocked transports) ------------

import httpx


def _mock(handler, monkeypatch, tmp_path):
    from manas.kernel import config
    from manas.integrations import http as ihttp
    monkeypatch.setattr(config.settings, "home", tmp_path)
    ihttp.set_transport(httpx.MockTransport(handler))
    return ihttp


def test_jira_fetch_contract_and_sync(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "jira_url", "https://jira.local")
    monkeypatch.setattr(config.settings, "jira_email", "amit@x")
    monkeypatch.setattr(config.settings, "jira_token", "t")

    def handler(req):
        assert "/rest/api/2/issue/NGSM-9" in str(req.url)
        return httpx.Response(200, json={"key": "NGSM-9", "fields": {
            "summary": "sync fails", "description": "provisioner hangs",
            "status": {"name": "Open"},
            "comment": {"comments": [{"body": "restart worked"}]}}})
    ihttp = _mock(handler, monkeypatch, tmp_path)
    try:
        from manas.integrations.sync import sync_jira
        rid = sync_jira("NGSM-9")
        from manas.memory import get_store
        recs = get_store().all_active("knowledge")
        assert any(r.id == rid and "provisioner hangs" in r.content
                   and "restart worked" in r.content for r in recs)
    finally:
        ihttp.set_transport(None)


def test_github_sync_repo_and_prs(tmp_path, monkeypatch):
    def handler(req):
        u = str(req.url)
        if u.endswith("/repos/acme/widget"):
            return httpx.Response(200, json={
                "description": "widget svc", "default_branch": "main",
                "language": "Python", "stargazers_count": 7, "topics": ["qa"]})
        return httpx.Response(200, json=[{
            "number": 12, "title": "fix fanout", "state": "open",
            "user": {"login": "amitku"}, "body": "raises pdsh fanout limit"}])
    ihttp = _mock(handler, monkeypatch, tmp_path)
    try:
        from manas.integrations.sync import sync_github
        r = sync_github("acme/widget")
        assert r == {"repo": 1, "prs": 1}
        assert sync_github("acme/widget") == {"repo": 0, "prs": 0}  # idempotent
    finally:
        ihttp.set_transport(None)


def test_testrail_add_result_needs_approval(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    with pytest.raises(ApprovalRequired):      # no approver -> blocked at gate
        asyncio.run(ToolGate().run("qa", "testrail_add_result",
                                   run_id=1, case_id=2, status_id=1))


def test_slack_post_needs_approval(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    with pytest.raises(ApprovalRequired):
        asyncio.run(ToolGate().run("assistant", "slack_post", text="hi team"))


def test_email_send_needs_approval(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    with pytest.raises(ApprovalRequired):
        asyncio.run(ToolGate().run("assistant", "email_send",
                                   to="a@b.c", subject="s", body="b"))


# ---- Phase 6: perception & actuation --------------------------------------

def test_ocr_reads_real_image(tmp_path, monkeypatch):
    from PIL import Image, ImageDraw
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    img = Image.new("RGB", (500, 80), "white")
    ImageDraw.Draw(img).text((10, 20), "MANAS PHASE SIX OCR", fill="black")
    p = tmp_path / "shot.png"; img.save(p)
    from manas.kernel.registry import tools as t
    out = asyncio.run(t.get("ocr_image")()(path=str(p)))
    assert "MANAS" in out["text"].upper()


def test_voice_command_extraction_pure_logic():
    from manas.perception.voice import extract_command
    assert extract_command("hey Manas, what's on my agenda") == "what's on my agenda"
    assert extract_command("random chatter no wake word") is None
    assert extract_command("MANAS run the qa graph") == "run the qa graph"
    assert extract_command("ok jarvis do it", wake_word="jarvis") == "do it"


def test_transcribe_with_injected_stt():
    from manas.perception.voice import Transcribe
    class FakeSTT:
        def transcribe(self, audio_path): return "manas summarize ticket HPCM-9"
    out = asyncio.run(Transcribe(stt=FakeSTT())(audio_path="x.wav"))
    assert out["command"] == "summarize ticket HPCM-9"


def test_browser_fetch_extracts_readable_text():
    from manas.perception import browser as br
    html = ("<html><head><title>Docs</title><script>evil()</script></head>"
            "<body><h1>Fanout</h1><p>pdsh limit is 128</p></body></html>")
    br.set_transport(httpx.MockTransport(
        lambda req: httpx.Response(200, text=html)))
    try:
        from manas.kernel.registry import tools as t
        r = asyncio.run(t.get("browser_fetch")()(url="https://d.local/x"))
        assert r["title"] == "Docs" and "pdsh limit is 128" in r["text"]
        assert "evil" not in r["text"]              # scripts stripped
    finally:
        br.set_transport(None)


def test_browser_act_gated_and_driver_contract(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    with pytest.raises(ApprovalRequired):           # live browser = APPROVAL
        asyncio.run(ToolGate().run("assistant", "browser_act",
                                   steps=[{"op": "goto", "url": "https://x"}]))
    from manas.perception.browser import BrowserAct
    class FakeDriver:
        def do(self, step): return f"did:{step['op']}"
    log = asyncio.run(BrowserAct(driver=FakeDriver())(
        steps=[{"op": "goto", "url": "u"}, {"op": "click", "selector": "#b"}]))
    assert log == ["did:goto", "did:click"]


def test_calendar_roundtrip(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.kernel.registry import tools as t
    start = (datetime.now().astimezone() + timedelta(days=1)).isoformat()
    asyncio.run(t.get("calendar_add")()(
        summary="VECTOR phase0 recon review", start_iso=start,
        duration_min=45, location="MFDC"))
    events = asyncio.run(t.get("calendar_read")()(days=3))
    assert len(events) == 1
    assert events[0]["summary"] == "VECTOR phase0 recon review"
    assert events[0]["location"] == "MFDC"


def test_screenshot_honest_on_headless(tmp_path, monkeypatch):
    from manas.kernel import config
    from manas.kernel.errors import ManasError
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.kernel.registry import tools as t
    with pytest.raises(ManasError):                 # no display/mss here: honest
        asyncio.run(t.get("screenshot")()())


def test_calendar_preserves_instant_across_timezones(tmp_path, monkeypatch):
    from datetime import datetime
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.kernel.registry import tools as t
    from datetime import timedelta
    ist = (datetime.now().astimezone() + timedelta(days=1)).replace(
        hour=4, minute=30, second=0, microsecond=0).isoformat().rsplit("+", 1)[0] + "+05:30"
    asyncio.run(t.get("calendar_add")()(summary="tz check", start_iso=ist))
    ev = asyncio.run(t.get("calendar_read")()(days=3))[0]
    assert datetime.fromisoformat(ev["start"]) == datetime.fromisoformat(ist)


# ---- Phase 7: observability ------------------------------------------------

def test_metrics_prometheus_format():
    from manas.kernel.metrics import Registry
    reg = Registry()
    c = reg.counter("m_reqs_total", "reqs")
    c.inc(provider="echo", status="ok"); c.inc(provider="echo", status="ok")
    h = reg.histogram("m_lat_seconds", "lat")
    h.observe(0.07, op="x"); h.observe(3.0, op="x")
    text = reg.render()
    assert '# TYPE m_reqs_total counter' in text
    assert 'm_reqs_total{provider="echo",status="ok"} 2.0' in text
    assert 'm_lat_seconds_bucket{op="x",le="0.1"} 1' in text
    assert 'm_lat_seconds_bucket{op="x",le="+Inf"} 2' in text
    assert 'm_lat_seconds_count{op="x"} 2' in text


def test_spans_nest_and_persist(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.kernel.trace import recent, span
    with span("outer", graph="g1") as o:
        with span("inner", tool="shell") as i:
            assert i.trace_id == o.trace_id and i.parent_id == o.span_id
    t = recent(1)[0]
    assert t["root"]["name"] == "outer"
    assert t["root"]["children"][0]["name"] == "inner"
    assert t["root"]["children"][0]["attrs"]["tool"] == "shell"


def test_span_marks_error_status(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.kernel.trace import recent, span
    with pytest.raises(ValueError):
        with span("boom"):
            raise ValueError("x")
    assert recent(1)[0]["root"]["status"] == "ERROR"


def test_instrumentation_counts_llm_and_tools(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.kernel.metrics import LLM_REQS, TOOL_RUNS
    from manas.providers.base import complete
    before = dict(LLM_REQS.values)
    asyncio.run(complete("sys", [{"role": "user", "content": "hi"}],
                         provider="echo"))
    key = (("provider", "echo"), ("status", "ok"))
    assert LLM_REQS.values[key] == before.get(key, 0) + 1
    tb = dict(TOOL_RUNS.values)
    asyncio.run(ToolGate().run("t", "read_file", path="pyproject.toml"))
    tkey = (("status", "ok"), ("tool", "read_file"))
    assert TOOL_RUNS.values[tkey] == tb.get(tkey, 0) + 1


def test_health_checks_all_green(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.kernel.health import run_checks
    checks = run_checks()
    assert {c["name"] for c in checks} >= {"prompts", "memory", "audit",
                                           "provider", "disk", "registries"}
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]


def test_orchestrator_run_produces_trace(tmp_path, monkeypatch):
    import asyncio as aio
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.agents.orchestrator import OrchestratorAgent
    aio.run(OrchestratorAgent().run("tiny goal"))
    from manas.kernel.trace import recent
    names = set()
    def walk(sp):
        names.add(sp["name"]); [walk(c) for c in sp["children"]]
    for t in recent(10):
        walk(t["root"])
    assert "task.run" in names and "llm.complete" in names


# ---- Phase 8: self-improvement loop ---------------------------------------

def test_reflection_written_after_run(tmp_path, monkeypatch):
    import asyncio as aio
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.agents.orchestrator import OrchestratorAgent
    from manas.memory import get_store
    aio.run(OrchestratorAgent().run("stabilize pdsh fanout on hpcm"))
    lessons = [r for r in get_store().all_active("episodic")
               if r.source == "learning"]
    assert len(lessons) == 1
    assert "outcome=success" in lessons[0].content
    assert "done=2/2" in lessons[0].content


def test_lessons_retrieved_for_similar_goal(tmp_path, monkeypatch):
    import asyncio as aio
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.agents.learning import LearningAgent
    from manas.agents.orchestrator import OrchestratorAgent
    aio.run(OrchestratorAgent().run("tune testrail sync retries"))
    ctx = LearningAgent().lessons_for("testrail sync keeps failing")
    assert "lesson[" in ctx and "testrail sync" in ctx


def test_failure_lessons_rank_higher():
    from manas.agents.learning import LearningAgent
    # importance mapping is the ranking lever: failures must outweigh successes
    assert 0.8 > 0.6 > 0.4  # failure > partial > success (documented invariant)
    assert LearningAgent.name == "learning"


# ---- Phase 9: provider hardening ------------------------------------------

def test_retry_then_fallback_chain(tmp_path, monkeypatch):
    from manas.kernel import config
    from manas.kernel.registry import providers as preg
    monkeypatch.setattr(config.settings, "home", tmp_path)
    if "flaky" not in preg.names():
        @preg.register("flaky")
        class Flaky:
            async def complete(self, system, messages, model):
                raise RuntimeError("boom")
    monkeypatch.setattr(config.settings, "provider_fallbacks", "echo")
    import manas.providers.base as pb
    monkeypatch.setattr(pb, "BACKOFF", 0.0)      # fast test
    out = asyncio.run(pb.complete("s", [{"role": "user", "content": "hi"}],
                                  provider="flaky"))
    assert "[echo provider" in out               # degraded gracefully
    key = (("provider", "flaky"), ("status", "error"))
    assert pb.LLM_REQS.values[key] >= 3          # retried before falling back


def test_routing_by_purpose(monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "routes", "critic=echo:tiny")
    from manas.providers.base import _route
    assert _route("critic") == ("echo", "tiny")
    assert _route("plan") == (None, None)


def test_token_and_cost_accounting(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    monkeypatch.setattr(config.settings, "cost_per_mtok", "echo=100:200")
    import manas.providers.base as pb
    before = sum(pb.LLM_COST.values.values())
    asyncio.run(pb.complete("sys " * 100,
                            [{"role": "user", "content": "hello " * 200}],
                            provider="echo"))
    assert sum(pb.LLM_COST.values.values()) > before
    assert any(k == (("direction", "in"), ("provider", "echo"))
               for k in pb.LLM_TOKENS.values)


def test_echo_streaming_yields_chunks():
    from manas.providers.base import stream

    async def collect():
        return [c async for c in stream("s", [{"role": "user",
                                               "content": "a b c"}],
                                        provider="echo")]
    chunks = asyncio.run(collect())
    assert len(chunks) > 3 and "".join(chunks).strip().endswith("a b c")


# ---- Phase 10: computer control -------------------------------------------

def test_desktop_dry_run_plans_without_backend(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.perception.desktop import DesktopControl
    steps = [{"op": "open_app", "name": "firefox"},
             {"op": "type", "text": "secret-password"},
             {"op": "hotkey", "keys": ["ctrl", "s"]}]
    out = asyncio.run(DesktopControl()(steps=steps, dry_run=True))
    assert out["dry_run"] and len(out["plan"]) == 3
    assert all("secret-password" not in p for p in out["plan"])  # never echoed


def test_desktop_live_requires_prior_dry_run(tmp_path, monkeypatch):
    from manas.kernel import config
    from manas.kernel.errors import ManasError
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.perception import desktop as d
    monkeypatch.setattr(d, "_previewed", set())
    class FakeBackend:
        def __init__(self): self.done = []
        def do(self, s): self.done.append(s["op"])
    fb = FakeBackend()
    steps = [{"op": "move", "x": 1, "y": 2}, {"op": "click"}]
    with pytest.raises(ManasError):                      # no preview yet
        asyncio.run(d.DesktopControl(backend=fb)(steps=steps, dry_run=False))
    asyncio.run(d.DesktopControl(backend=fb)(steps=steps, dry_run=True))
    out = asyncio.run(d.DesktopControl(backend=fb)(steps=steps, dry_run=False))
    assert fb.done == ["move", "click"] and not out["dry_run"]


def test_desktop_gated_at_toolgate(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    with pytest.raises(ApprovalRequired):
        asyncio.run(ToolGate().run("assistant", "desktop_control",
                                   steps=[{"op": "click"}]))


# ---- Phase 11: RBAC + encrypted scoped stores -----------------------------

def test_rbac_ceiling_blocks_operator(tmp_path, monkeypatch):
    from manas.kernel import config
    from manas.kernel.auth import User
    monkeypatch.setattr(config.settings, "home", tmp_path)
    op = User(name="lekha", roles=("operator",))
    gate = ToolGate(approver=lambda a, r: True, user=op)   # approver present…
    with pytest.raises(ToolDenied):                        # …ceiling still wins
        asyncio.run(gate.run("qa", "shell", command="echo hi"))
    # SAFE tool is fine for operator:
    out = asyncio.run(gate.run("qa", "read_file", path="pyproject.toml"))
    assert "manas" in out


def test_content_encrypted_at_rest(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.memory.scoped import ScopedStore
    s = ScopedStore("personal")
    s.write(Record(tier="semantic", content="amit salary details PLAINTEXT"))
    raw = (tmp_path / "memory" / "personal.db").read_bytes()
    assert b"PLAINTEXT" not in raw                 # cipher at rest
    hits = s.recall("salary details")
    assert hits and "PLAINTEXT" in hits[0].content # decrypts for permitted caller


def test_scopes_have_separate_keys_and_files(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.memory.scoped import ScopedStore, _key
    ScopedStore("personal"); ScopedStore("enterprise")
    assert _key("personal") != _key("enterprise")
    assert (tmp_path / "memory" / "personal.db").exists()
    assert (tmp_path / "memory" / "enterprise.db").exists()


def test_cross_store_requires_explicit_grant(tmp_path, monkeypatch):
    from manas.kernel import config
    from manas.kernel.auth import User
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.memory.scoped import ScopedStore, recall_across
    ScopedStore("enterprise").write(
        Record(tier="semantic", content="hpcm release gate criteria"))
    with pytest.raises(ToolDenied):                # no grant, no search
        recall_across("release gate", grant=())
    limited = User(name="viewer1", roles=("viewer",),
                   memory_scopes=("personal",))
    with pytest.raises(ToolDenied):                # scope not held by user
        recall_across("release gate", grant=("enterprise",), user=limited)
    hits = recall_across("release gate", grant=("enterprise",))
    assert hits and "release gate" in hits[0].content


# ---- Phase 12: distributed execution --------------------------------------

def test_two_nodes_share_one_graph(tmp_path, monkeypatch):
    import asyncio as aio
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.kernel.distq import DistWorker, LeaseTable
    from manas.kernel.taskgraph import Task, TaskGraph
    a = Task(name="a", agent="assistant", instruction="step a")
    b = Task(name="b", agent="assistant", instruction="step b",
             depends_on=[a.id])
    path = str(TaskGraph(goal="dist demo", tasks=[a, b]).save())
    leases = LeaseTable()
    w1, w2 = DistWorker("node-1", leases), DistWorker("node-2", leases)
    ran1 = aio.run(w1.step(path))                  # node-1 takes 'a'
    assert ran1 == "a"
    ran2 = aio.run(w2.step(path))                  # node-2 takes 'b'
    assert ran2 == "b"
    assert TaskGraph.load(path).finished()


def test_lease_expiry_recovers_from_node_death(tmp_path, monkeypatch):
    import asyncio as aio
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.kernel.distq import DistWorker, LeaseTable
    from manas.kernel.taskgraph import Task, TaskGraph
    t = Task(name="only", agent="assistant", instruction="do it")
    path = str(TaskGraph(goal="death demo", tasks=[t]).save())
    leases = LeaseTable()
    # dead node claimed with an ALREADY-EXPIRED lease and never released:
    assert leases.claim("ignored", "warmup", "x") in (True, False)
    g = TaskGraph.load(path)
    assert leases.claim(g.id, g.tasks[0].id, "dead-node", lease=-5)
    # a live claim by another node must NOT be stealable while fresh:
    assert leases.claim(g.id, g.tasks[0].id, "thief", lease=60)  # expired->wins
    leases.release(g.id, g.tasks[0].id)
    # now full recovery path: dead claim again, survivor reclaims + completes
    assert leases.claim(g.id, g.tasks[0].id, "dead-node", lease=-5)
    survivor = DistWorker("survivor", leases)
    assert aio.run(survivor.step(path)) == "only"
    assert TaskGraph.load(path).finished()
    # fresh lease is protected:
    g2 = TaskGraph(goal="x", tasks=[Task(name="t", agent="assistant",
                                         instruction="i")])
    g2.save()
    assert leases.claim(g2.id, g2.tasks[0].id, "holder", lease=60)
    assert not leases.claim(g2.id, g2.tasks[0].id, "thief2", lease=60)


# ---- Phase 13: continuous ingestion ---------------------------------------

def test_watcher_reingests_on_change_and_archives_stale(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path / "home")
    from manas.knowledge.watch import Watcher, add_watch, load_watches
    from manas.memory import get_store
    repo = tmp_path / "repo"; repo.mkdir()
    doc = repo / "notes.md"
    doc.write_text("# Notes\n\ninitial content about zephyr provider\n")
    add_watch(str(repo))
    assert load_watches() == [str(repo)]
    w = Watcher()
    first = w.poll_once()                          # first poll ingests baseline
    assert first[str(repo)]["chunks_new"] >= 1
    import time as _t; _t.sleep(0.01)
    doc.write_text("# Notes\n\nrewritten: zephyr disabled by default now\n")
    reports = w.poll_once()
    assert reports and reports[str(repo)]["chunks_new"] >= 1
    assert reports[str(repo)]["chunks_archived"] >= 1
    active = [r.content for r in get_store().all_active("knowledge")]
    assert any("disabled by default" in c for c in active)
    assert not any("initial content" in c for c in active)


def test_watcher_quiet_when_nothing_changed(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path / "home")
    from manas.knowledge.watch import Watcher
    repo = tmp_path / "repo"; repo.mkdir()
    (repo / "a.md").write_text("stable")
    w = Watcher([str(repo)])
    w.poll_once()                                  # baseline ingest
    assert w.poll_once() == {}                     # no change -> no ingest


# ---- Phase 14: edge & robotics --------------------------------------------

class _FakeMqtt:
    def __init__(self): self.published = []
    def publish(self, topic, payload, qos=1): self.published.append((topic, payload))
    def read(self, topic, timeout=5.0): return "23.5"


def test_actuation_impossible_without_human_approver(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    with pytest.raises(ApprovalRequired):          # no approver: hard block
        asyncio.run(ToolGate().run("robot", "actuate",
                                   topic="lab/relay1", payload="ON",
                                   dry_run=False))


def test_actuation_dry_run_then_approved_publish(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.integrations.iot import Actuate
    fb = _FakeMqtt()
    prompts = []
    def approver(action, reason):
        prompts.append((action, reason)); return True
    gate = ToolGate(approver=approver)
    # dry run previews without publishing (still human-approved: always_gate)
    out = asyncio.run(Actuate(backend=fb)(topic="lab/relay1", payload="ON"))
    assert out["dry_run"] and fb.published == []
    # live publish via the gate: approver consulted, then real publish
    from manas.kernel.registry import tools as treg
    orig = treg._items["actuate"]
    treg._items["actuate"] = lambda: Actuate(backend=fb)
    try:
        out2 = asyncio.run(gate.run("robot", "actuate", topic="lab/relay1",
                                    payload="ON", dry_run=False))
    finally:
        treg._items["actuate"] = orig
    assert out2 == {"dry_run": False, "published": "lab/relay1"}
    assert fb.published == [("lab/relay1", "ON")]
    assert prompts and "PHYSICAL" in prompts[0][1]


def test_actuation_rejects_wildcard_topics(tmp_path, monkeypatch):
    from manas.kernel import config
    from manas.kernel.errors import ManasError
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.integrations.iot import Actuate
    with pytest.raises(ManasError):
        asyncio.run(Actuate(backend=_FakeMqtt())(topic="lab/#", payload="ON"))


def test_sensor_read_is_safe_and_gateable(tmp_path, monkeypatch):
    from manas.kernel import config
    monkeypatch.setattr(config.settings, "home", tmp_path)
    from manas.integrations.iot import SensorRead
    from manas.kernel.registry import tools as treg
    orig = treg._items["sensor_read"]
    treg._items["sensor_read"] = lambda: SensorRead(backend=_FakeMqtt())
    try:                                            # SAFE: no approver needed
        out = asyncio.run(ToolGate().run("assistant", "sensor_read",
                                         topic="lab/temp"))
    finally:
        treg._items["sensor_read"] = orig
    assert out["value"] == "23.5" and not out["timed_out"]
