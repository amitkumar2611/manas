"""Curator agent: keeps memory healthy (prompts/40_memory.md rules).

Mechanical passes (no LLM needed): importance decay, stale-record archival.
LLM pass (when a real provider is configured): promote recurring episodic
themes into distilled semantic facts. Never deletes — only archives, audited.
"""
import time

from manas.agents.base import BaseAgent
from manas.kernel.registry import agents
from manas.memory import get_store
from manas.memory.embed import cosine, get_embedder
from manas.memory.store import Record

DAY = 86400


@agents.register("curator")
class CuratorAgent(BaseAgent):
    name = "curator"
    purpose = "summarize, compress, promote episodic->semantic, decay importance"
    prompt_layers = ("40_memory.md",)
    memory_scopes = ("working", "conversation", "episodic", "semantic")

    async def curate(self) -> dict:
        store = get_store()
        report = {"decayed": 0, "archived": 0, "promoted": 0}
        now = time.time()

        # 1) Decay: importance erodes with age unless the record keeps being used.
        for r in store.all_active():
            age_days = (now - r.created) / DAY
            usage_boost = min(0.2, r.access_count * 0.02)
            decayed = max(0.05, r.importance * (0.995 ** age_days) + usage_boost)
            if abs(decayed - r.importance) > 0.01:
                store.decay(r.id, r.version, round(decayed, 3))
                report["decayed"] += 1

        # 2) Archive: stale, unimportant, never-accessed working/conversation.
        for r in store.all_active():
            stale = (now - r.last_access) > 14 * DAY
            if r.tier in ("working", "conversation") and stale \
                    and r.importance < 0.2 and r.access_count == 0:
                store.archive(r.id, self.name, "stale low-value record")
                report["archived"] += 1

        # 3) Promote: clusters of similar episodic records -> one semantic fact.
        emb = get_embedder()
        episodic = store.all_active("episodic")
        vecs = {r.id: emb.embed(r.content) for r in episodic}
        seen: set[str] = set()
        for r in episodic:
            if r.id in seen:
                continue
            cluster = [o for o in episodic if o.id not in seen
                       and cosine(vecs[r.id], vecs[o.id]) > 0.75]
            if len(cluster) >= 3:
                seen.update(o.id for o in cluster)
                bullet = "\n".join(f"- {o.content}" for o in cluster[:10])
                try:
                    fact = await self.think([{"role": "user", "content":
                        "Distill these related events into ONE durable fact "
                        f"(a single sentence):\n{bullet}"}])
                except Exception:
                    fact = f"recurring theme ({len(cluster)}x): {cluster[0].content[:120]}"
                store.write(Record(tier="semantic", content=fact.strip()[:500],
                                   source="curator", importance=0.7,
                                   links=[o.id for o in cluster]))
                report["promoted"] += 1
        return report
