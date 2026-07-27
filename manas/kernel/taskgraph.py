"""Task DAG: the executable form of a plan (prompts/50_planning.md).

Graphs are artifacts — persisted after every state change, so any run can
be interrupted (crash, reboot, NEED_HUMAN) and resumed exactly where it was.
"""
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from manas.kernel.config import settings
from manas.kernel.errors import ManasError

STATUSES = ("PENDING", "RUNNING", "DONE", "FAILED", "NEED_HUMAN")


@dataclass
class Task:
    name: str
    agent: str                                   # which agent executes it
    instruction: str
    depends_on: list[str] = field(default_factory=list)   # task ids
    done_criteria: str = ""
    risk_level: str = "SAFE"                     # SAFE | REVIEW | APPROVAL
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: str = "PENDING"
    result: str = ""
    feedback: str = ""                           # critic notes fed into retries
    attempts: int = 0


@dataclass
class TaskGraph:
    goal: str
    tasks: list[Task] = field(default_factory=list)
    id: str = field(default_factory=lambda: time.strftime("%Y%m%d-%H%M%S"))

    # -- validation ---------------------------------------------------------
    def validate(self) -> None:
        ids = {t.id for t in self.tasks}
        for t in self.tasks:
            missing = set(t.depends_on) - ids
            if missing:
                raise ManasError(f"task '{t.name}' depends on unknown {missing}")
        seen: set[str] = set()
        remaining = list(self.tasks)
        while remaining:                          # Kahn's algorithm: cycle check
            ready = [t for t in remaining if set(t.depends_on) <= seen]
            if not ready:
                raise ManasError("task graph contains a cycle")
            seen.update(t.id for t in ready)
            remaining = [t for t in remaining if t.id not in seen]

    # -- scheduling ---------------------------------------------------------
    def ready(self) -> list[Task]:
        done = {t.id for t in self.tasks if t.status == "DONE"}
        return [t for t in self.tasks
                if t.status == "PENDING" and set(t.depends_on) <= done]

    def finished(self) -> bool:
        return all(t.status == "DONE" for t in self.tasks)

    def blocked(self) -> bool:
        return (not self.finished() and not self.ready()
                and not any(t.status == "RUNNING" for t in self.tasks))

    def context_for(self, task: Task) -> str:
        """Results of completed dependencies, injected into the worker prompt."""
        by_id = {t.id: t for t in self.tasks}
        parts = [f"### result of '{by_id[d].name}'\n{by_id[d].result}"
                 for d in task.depends_on if by_id[d].result]
        return "\n\n".join(parts)

    # -- persistence (resumability) ----------------------------------------
    @property
    def path(self) -> Path:
        settings.ensure_dirs()
        return settings.home / "plans" / f"graph-{self.id}.json"

    def save(self) -> Path:
        self.path.write_text(json.dumps(
            {"goal": self.goal, "id": self.id,
             "tasks": [asdict(t) for t in self.tasks]}, indent=2))
        return self.path

    @classmethod
    def load(cls, path: str | Path) -> "TaskGraph":
        data = json.loads(Path(path).read_text())
        g = cls(goal=data["goal"], id=data["id"],
                tasks=[Task(**t) for t in data["tasks"]])
        for t in g.tasks:                         # crash mid-run -> retry task
            if t.status == "RUNNING":
                t.status = "PENDING"
        return g
