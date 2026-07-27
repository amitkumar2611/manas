"""Orchestrator: goal -> task DAG -> phased execution with critic loop.

Owns the graph; workers own single tasks (prompts/10_agent_rules.md).
Retries are capped at 2 and always carry changed strategy (critic feedback).
Every state change is persisted -> any run is resumable.
"""
import asyncio
import json

from manas.agents.base import BaseAgent
from manas.agents.critic import CriticAgent
from manas.kernel.config import settings
from manas.kernel.errors import ApprovalRequired
from manas.kernel.events import Event, bus
from manas.kernel.log import get_logger
from manas.kernel.metrics import TASKS
from manas.kernel.trace import span
from manas.kernel.registry import agents
from manas.kernel.taskgraph import Task, TaskGraph

log = get_logger("orchestrator")
MAX_ATTEMPTS = 3          # 1 try + 2 retries with changed strategy
NEEDS_REVIEW = ("REVIEW", "APPROVAL")


@agents.register("orchestrator")
class OrchestratorAgent(BaseAgent):
    name = "orchestrator"
    purpose = "own the task graph; dispatch, review, retry, escalate"
    prompt_layers = ("10_agent_rules.md", "50_planning.md")
    memory_scopes = ("working", "episodic")

    # -- planning: goal -> graph -------------------------------------------
    async def build_graph(self, goal: str) -> TaskGraph:
        from manas.agents.learning import LearningAgent
        lessons = LearningAgent().lessons_for(goal)
        lesson_block = (f"Lessons from similar past runs (apply them):\n"
                        f"{lessons}\n\n" if lessons else "")
        raw = await self.think([{"role": "user", "content":
            f"{lesson_block}GOAL: {goal}\n\nDecompose into 2-6 tasks. Reply with ONLY a JSON "
            "array, each item: {\"name\": str, \"agent\": \"assistant\", "
            "\"instruction\": str, \"depends_on\": [names of prior tasks], "
            "\"done_criteria\": str, \"risk_level\": \"SAFE|REVIEW\"}. "
            "First task MUST be recon of current state (Phase 0)."}])
        graph = TaskGraph(goal=goal)
        try:
            items = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
            by_name: dict[str, str] = {}
            for it in items:
                t = Task(name=it["name"],
                         agent=it.get("agent", "assistant"),
                         instruction=it["instruction"],
                         done_criteria=it.get("done_criteria", ""),
                         risk_level=it.get("risk_level", "SAFE"))
                t.depends_on = [by_name[d] for d in it.get("depends_on", [])
                                if d in by_name]
                by_name[t.name] = t.id
                graph.tasks.append(t)
        except (ValueError, KeyError, json.JSONDecodeError):
            # No parseable plan (e.g. echo provider): honest minimal fallback
            # so the machinery still runs offline — labeled as such.
            recon = Task(name="recon", agent="assistant", risk_level="SAFE",
                         instruction=f"Phase 0 recon for goal: {goal}. "
                                     "List what is known and unknown.")
            execute = Task(name="execute", agent="assistant",
                           instruction=f"Address the goal: {goal}",
                           depends_on=[recon.id], risk_level="REVIEW",
                           done_criteria="goal addressed or blockers named")
            graph.tasks = [recon, execute]
            log.info("plan fallback=minimal reason=no parseable JSON from provider")
        graph.validate()
        graph.save()
        return graph

    # -- execution -----------------------------------------------------------
    async def execute(self, graph: TaskGraph) -> TaskGraph:
        critic = CriticAgent()
        while not graph.finished():
            batch = graph.ready()
            if not batch:
                if graph.blocked():
                    log.info(f"graph={graph.id} blocked; human attention needed")
                    break
                await asyncio.sleep(0.05)
                continue
            await asyncio.gather(*(self._run_task(graph, t, critic)
                                   for t in batch))
        graph.save()
        from manas.agents.learning import LearningAgent
        await LearningAgent().reflect(graph)      # self-improvement loop closes here
        await self.remember(
            f"graph {graph.id} '{graph.goal[:120]}' -> "
            f"{sum(t.status == 'DONE' for t in graph.tasks)}/{len(graph.tasks)} done",
            importance=0.6)
        return graph

    async def _run_task(self, graph: TaskGraph, task: Task,
                        critic: CriticAgent) -> None:
        with span("task.run", graph=graph.id, task=task.name, agent=task.agent):
            worker: BaseAgent = agents.get(
                task.agent if task.agent in agents.names() else "assistant")()
            task.status = "RUNNING"
            graph.save()                          # resumable at every step
            await bus.publish(Event("task.started",
                                    {"graph": graph.id, "task": task.name},
                                    source=self.name))
            while task.attempts < MAX_ATTEMPTS:
                task.attempts += 1
                prompt = task.instruction
                ctx = graph.context_for(task)
                if ctx:
                    prompt = (f"Context from completed prerequisite tasks:\n"
                              f"{ctx}\n\n{prompt}")
                if task.feedback:                 # changed strategy, never identical retry
                    prompt += ("\n\nPrevious attempt was rejected. "
                               f"Reviewer feedback:\n{task.feedback}")
                try:
                    task.result = await worker.think(
                        [{"role": "user", "content": prompt}])
                except ApprovalRequired as e:
                    task.status, task.result = "NEED_HUMAN", str(e)
                    break
                except Exception as e:            # noqa: BLE001 — recorded, not hidden
                    task.feedback = f"attempt {task.attempts} raised: {e}"
                    task.status = "FAILED"
                    continue
                if task.risk_level in NEEDS_REVIEW:
                    ok, notes = await critic.review(task)
                    if not ok:
                        task.feedback, task.status = notes, "FAILED"
                        continue
                    task.result += f"\n\n[critic] {notes}"
                task.status = "DONE"
                break
        TASKS.inc(status=task.status)
        graph.save()
        await bus.publish(Event("task.finished",
                                {"graph": graph.id, "task": task.name,
                                 "status": task.status}, source=self.name))

    async def run(self, goal: str) -> TaskGraph:
        return await self.execute(await self.build_graph(goal))

    async def resume(self, path: str) -> TaskGraph:
        return await self.execute(TaskGraph.load(path))
