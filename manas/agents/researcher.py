"""Researcher agent: RAG over the knowledge tier with source attribution."""
from manas.agents.base import BaseAgent
from manas.kernel.config import settings
from manas.kernel.registry import agents


@agents.register("researcher")
class ResearcherAgent(BaseAgent):
    name = "researcher"
    purpose = "answer questions over the ingested knowledge corpus, with sources"
    prompt_layers = ("40_memory.md", "60_output_contract.md")
    memory_scopes = ("working", "episodic")

    async def ask(self, question: str, k: int = 6) -> str:
        hits = self.memory.recall(question, tier="knowledge", k=k)
        if not hits:
            return ("No knowledge records matched. Ingest a corpus first: "
                    "`manas ingest <path>`.")
        ctx = "\n\n---\n".join(f"[source: {r.source}]\n{r.content[:1500]}"
                               for r in hits)
        if settings.provider == "echo":       # honest offline mode: raw retrieval
            srcs = "\n".join(f"- {r.source}" for r in hits)
            return (f"[echo provider — returning retrieval only, no synthesis]\n"
                    f"Top sources:\n{srcs}\n\n{ctx[:3000]}")
        answer = await self.think([{"role": "user", "content":
            f"Answer strictly from these excerpts; cite [source: ...] paths "
            f"you used; say so if the corpus is insufficient.\n\n{ctx}\n\n"
            f"QUESTION: {question}"}])
        await self.remember(f"researched: {question[:150]}", importance=0.4)
        return answer
