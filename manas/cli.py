"""MANAS CLI — Phase 1 presentation layer."""
import asyncio

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from manas import __version__
from manas.agents.assistant import AssistantAgent
from manas.agents.planner import PlannerAgent
from manas.kernel.config import settings
from manas.kernel.registry import agents, memories, providers, tools
from manas.tools.gate import ToolGate

app = typer.Typer(help="MANAS — Modular Autonomous Neural Agent System")
console = Console()


def _human_approver(action: str, reason: str) -> bool:
    return typer.confirm(f"APPROVAL: allow '{action}'? ({reason})")


@app.command()
def status() -> None:
    """Show kernel status: registered components and active config."""
    console.print(Panel.fit(
        f"[bold cyan]MANAS[/] v{__version__}\n"
        f"provider   : {settings.provider} (model: {settings.model or 'default'})\n"
        f"memory     : {settings.memory_backend} / embedder: {settings.embedder}\n"
        f"home       : {settings.home}\n"
        f"agents     : {', '.join(agents.names())}\n"
        f"tools      : {', '.join(tools.names())}\n"
        f"providers  : {', '.join(providers.names())}\n"
        f"memories   : {', '.join(memories.names())}",
        title="kernel status"))


@app.command()
def chat() -> None:
    """Interactive chat with the assistant agent (memory-aware)."""
    agent = AssistantAgent(gate=ToolGate(approver=_human_approver))
    history: list[dict] = []
    console.print("[dim]MANAS chat — Ctrl+C or 'exit' to quit[/]")
    while True:
        msg = console.input("[bold green]you[/] > ")
        if msg.strip().lower() in {"exit", "quit"}:
            break
        reply = asyncio.run(agent.chat(msg, history))
        history += [{"role": "user", "content": msg},
                    {"role": "assistant", "content": reply}]
        console.print(Panel(escape(reply), title="manas", border_style="cyan"))


@app.command()
def plan(goal: str) -> None:
    """Turn a goal into a phased, risk-labeled plan (saved to ~/.manas/plans)."""
    result = asyncio.run(PlannerAgent().plan(goal))
    console.print(Panel(escape(result), title="plan", border_style="magenta"))


@app.command()
def remember(text: str, tier: str = "semantic", importance: float = 0.7) -> None:
    """Write a fact directly into memory."""
    from manas.memory import get_store
    from manas.memory.store import Record
    rid = get_store().write(Record(tier=tier, content=text,
                                     importance=importance, source="cli"))
    console.print(f"stored \\[{tier}] id={rid}")


@app.command()
def recall(query: str, tier: str = None) -> None:  # type: ignore[assignment]
    """Query memory with scored retrieval."""
    from manas.memory import get_store
    for r in get_store().recall(query, tier=tier):
        console.print(f"\\[{r.tier}] ({r.importance:.2f}) {escape(r.content)}")


@app.command()
def run(goal: str) -> None:
    """Goal -> task DAG -> execute with critic review. Resumable artifact."""
    from manas.agents.orchestrator import OrchestratorAgent
    g = asyncio.run(OrchestratorAgent().run(goal))
    _render_graph(g)


@app.command()
def resume(path: str) -> None:
    """Resume an interrupted graph from ~/.manas/plans/graph-*.json."""
    from manas.agents.orchestrator import OrchestratorAgent
    g = asyncio.run(OrchestratorAgent().resume(path))
    _render_graph(g)


@app.command()
def graphs() -> None:
    """List saved task graphs and their completion state."""
    import json
    from manas.kernel.taskgraph import TaskGraph
    settings.ensure_dirs()
    for f in sorted((settings.home / "plans").glob("graph-*.json")):
        d = json.loads(f.read_text())
        done = sum(t["status"] == "DONE" for t in d["tasks"])
        console.print(f"{f.name}  {done}/{len(d['tasks'])} done  "
                      f"goal: {escape(d['goal'][:60])}")


def _render_graph(g) -> None:
    icons = {"DONE": "[green]DONE[/]", "FAILED": "[red]FAIL[/]",
             "NEED_HUMAN": "[yellow]HUMAN[/]", "PENDING": "[dim]PEND[/]",
             "RUNNING": "RUN"}
    lines = [f"goal: {escape(g.goal)}", f"saved: {g.path}"]
    for t in g.tasks:
        lines.append(f"{icons[t.status]:>18s}  {escape(t.name)}  (agent={t.agent}, "
                     f"risk={t.risk_level}, attempts={t.attempts})")
    console.print(Panel("\n".join(lines), title=f"graph {g.id}",
                        border_style="magenta"))


@app.command()
def ingest(path: str, tickets: bool = typer.Option(False, "--tickets",
           help="treat PATH as a JSON file of ticket(s)")) -> None:
    """Ingest a file, directory, or repo into the knowledge tier (idempotent)."""
    from manas.knowledge import engine
    if tickets:
        ids = engine.ingest_ticket_file(path)
        console.print(f"ingested {len(ids)} ticket(s)")
    else:
        console.print(engine.ingest_path(path))


@app.command()
def ask(question: str) -> None:
    """RAG answer over ingested knowledge, with source attribution."""
    from manas.agents.researcher import ResearcherAgent
    console.print(Panel(escape(asyncio.run(ResearcherAgent().ask(question))),
                        title="researcher", border_style="cyan"))


@app.command()
def sync(source: str, ref: str) -> None:
    """Pull from a live system into knowledge. source: jira|github  ref: key|owner/repo"""
    from manas.integrations import sync as sy
    from manas.kernel.errors import ManasError
    try:
        if source == "jira":
            console.print(f"ingested ticket record {sy.sync_jira(ref)}")
        elif source == "github":
            console.print(sy.sync_github(ref))
        else:
            console.print("[red]source must be 'jira' or 'github'[/]")
    except ManasError as e:
        console.print(f"[red]sync failed:[/] {escape(str(e))}")
        raise typer.Exit(1)


@app.command()
def ocr(path: str) -> None:
    """Read text out of an image (screenshot understanding)."""
    from manas.kernel.registry import tools as t
    console.print(escape(asyncio.run(t.get("ocr_image")()(path=path))["text"]))


@app.command()
def browse(url: str) -> None:
    """Fetch a URL as readable text."""
    from manas.kernel.registry import tools as t
    r = asyncio.run(t.get("browser_fetch")()(url=url))
    console.print(Panel(escape(r["text"][:2500]), title=escape(r["title"] or url),
                        border_style="cyan"))


@app.command()
def agenda(days: int = 7) -> None:
    """Upcoming calendar events (local .ics store)."""
    from manas.kernel.registry import tools as t
    events = asyncio.run(t.get("calendar_read")()(days=days))
    if not events:
        console.print("no events in window")
    for e in events:
        console.print(f"{e['start']}  {escape(e['summary'])}"
                      + (f"  @ {escape(e['location'])}" if e['location'] else ""))


@app.command("calendar-add")
def calendar_add(summary: str, start_iso: str, duration_min: int = 30,
                 location: str = "") -> None:
    """Add an event to the local calendar."""
    from manas.kernel.registry import tools as t
    console.print(asyncio.run(t.get("calendar_add")()(
        summary=summary, start_iso=start_iso,
        duration_min=duration_min, location=location)))


@app.command()
def worker(graph: str = typer.Argument(""), node_id: str = "node-1",
           all: bool = typer.Option(False, "--all",
                                    help="serve every graph in ~/.manas/plans")) -> None:
    """Run a distributed worker node (lease-coordinated, safe to scale out)."""
    from manas.kernel.distq import DistWorker
    w = DistWorker(node_id)
    if graph:
        g = asyncio.run(w.run_until_done(graph))
        _render_graph(g)
        return
    if not all:
        console.print("give a graph path or --all"); raise typer.Exit(1)
    import time as _t
    console.print(f"[dim]worker {node_id} polling ~/.manas/plans[/]")
    while True:
        for f in sorted((settings.home / "plans").glob("graph-*.json")):
            asyncio.run(w.step(str(f)))
        _t.sleep(1)


@app.command()
def watch(path: str = typer.Argument(""), interval: float = 5.0,
          once: bool = typer.Option(False, "--once",
                                    help="single poll cycle then exit")) -> None:
    """Continuously re-ingest a path on change (stale chunks auto-archived)."""
    from manas.knowledge.watch import Watcher, add_watch
    if path:
        add_watch(path)
    w = Watcher()
    if not w.paths:
        console.print("nothing to watch — give a path"); raise typer.Exit(1)
    if once:
        console.print(w.poll_once() or "no changes")
        return
    w.run_forever(interval)


@app.command()
def doctor() -> None:
    """Deep health checks across every layer (exit 1 if any fail)."""
    from manas.kernel.health import run_checks
    checks = run_checks()
    for c in checks:
        mark = "[green]OK [/]" if c["ok"] else "[red]FAIL[/]"
        console.print(f"{mark} {c['name']:<11s} {c['ms']:>7.1f}ms  {c['detail']}")
    if not all(c["ok"] for c in checks):
        raise typer.Exit(1)


@app.command()
def metrics() -> None:
    """Dump kernel metrics (Prometheus text format)."""
    from manas.kernel.metrics import registry as mreg
    console.print(mreg.render(), highlight=False)


@app.command()
def traces(n: int = 3) -> None:
    """Show recent traces as span trees."""
    from manas.kernel.trace import recent

    def render(sp, depth=0):
        console.print(f"{'  ' * depth}{sp['name']} \\[{sp['status']}] "
                      f"{sp['ms']}ms {escape(str(sp['attrs']))}")
        for c in sp["children"]:
            render(c, depth + 1)

    for t in recent(n):
        console.print(f"[bold]trace {t['trace_id']}[/]")
        render(t["root"], 1)


@app.command()
def lessons(query: str = typer.Argument("")) -> None:
    """Lessons distilled from past runs (fed automatically into new plans)."""
    from manas.agents.learning import LearningAgent
    out = LearningAgent().lessons_for(query or "recent runs", k=10)
    console.print(out or "no lessons recorded yet — run some graphs first",
                  markup=False)


@app.command()
def curate() -> None:
    """Run the curator: decay importance, archive stale, promote themes."""
    from manas.agents.curator import CuratorAgent
    console.print(asyncio.run(CuratorAgent().curate()))


@app.command("memory-stats")
def memory_stats() -> None:
    """Active record counts per memory tier."""
    from manas.memory import get_store
    for tier, n in get_store().stats().items():
        console.print(f"{tier:14s} {n}")


if __name__ == "__main__":
    app()
