"""Distributed graph execution: multiple worker nodes share one task graph.

Coordination model (deliberately boring and debuggable):
- Graph state lives in the shared graph-*.json (shared FS: PVC/NFS in k8s).
- Claims live in a SQLite lease table: a worker atomically claims a ready
  task for LEASE seconds and heartbeats while working.
- Node death = lease expiry: any other worker may reclaim and re-run the
  task (tasks are idempotent-by-retry per Layer 10; RUNNING resets to
  PENDING exactly like crash-resume in Phase 3).
"""
import sqlite3
import time

from manas.agents.critic import CriticAgent
from manas.agents.orchestrator import OrchestratorAgent
from manas.kernel.config import settings
from manas.kernel.log import get_logger
from manas.kernel.taskgraph import TaskGraph

log = get_logger("distq")
LEASE_SECONDS = 60


class LeaseTable:
    def __init__(self) -> None:
        settings.ensure_dirs()
        self.db = sqlite3.connect(settings.home / "plans" / "claims.db",
                                  isolation_level=None)   # autocommit
        self.db.execute("""CREATE TABLE IF NOT EXISTS claims (
            graph_id TEXT, task_id TEXT, node TEXT, lease_until REAL,
            PRIMARY KEY (graph_id, task_id))""")

    def claim(self, graph_id: str, task_id: str, node: str,
              lease: float = LEASE_SECONDS) -> bool:
        """Atomic: succeeds iff unclaimed OR the existing lease has expired."""
        now = time.time()
        cur = self.db.execute(
            """INSERT INTO claims VALUES (?,?,?,?)
               ON CONFLICT(graph_id, task_id) DO UPDATE
               SET node=excluded.node, lease_until=excluded.lease_until
               WHERE claims.lease_until < ?""",
            (graph_id, task_id, node, now + lease, now))
        won = self.db.execute(
            "SELECT node FROM claims WHERE graph_id=? AND task_id=?",
            (graph_id, task_id)).fetchone()[0] == node and cur is not None
        return won

    def release(self, graph_id: str, task_id: str) -> None:
        self.db.execute("DELETE FROM claims WHERE graph_id=? AND task_id=?",
                        (graph_id, task_id))


class DistWorker:
    """One worker node. step() claims and executes at most one ready task."""

    def __init__(self, node_id: str, leases: LeaseTable | None = None) -> None:
        self.node = node_id
        self.leases = leases or LeaseTable()
        self.orc = OrchestratorAgent()
        self.critic = CriticAgent()

    async def step(self, graph_path: str) -> str | None:
        graph = TaskGraph.load(graph_path)     # resets orphaned RUNNING->PENDING
        ready = graph.ready()
        for task in ready:
            if not self.leases.claim(graph.id, task.id, self.node):
                continue                        # another live node owns it
            log.info(f"node={self.node} claimed task={task.name}")
            try:
                await self.orc._run_task(graph, task, self.critic)
            finally:
                self.leases.release(graph.id, task.id)
            return task.name
        return None                             # nothing claimable right now

    async def run_until_done(self, graph_path: str,
                             poll: float = 0.2) -> TaskGraph:
        import asyncio
        while True:
            graph = TaskGraph.load(graph_path)
            if graph.finished() or graph.blocked():
                return graph
            if await self.step(graph_path) is None:
                await asyncio.sleep(poll)
