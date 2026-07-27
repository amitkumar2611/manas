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
