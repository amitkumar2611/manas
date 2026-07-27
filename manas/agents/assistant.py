"""Assistant agent: the front door. Converses, recalls memory, delegates."""
from manas.agents.base import BaseAgent
from manas.kernel.registry import agents


@agents.register("assistant")
class AssistantAgent(BaseAgent):
    name = "assistant"
    purpose = "primary conversational interface; recalls memory, answers, delegates"
    prompt_layers = ("40_memory.md", "60_output_contract.md")
    tool_allowlist = ("read_file",)
    memory_scopes = ("working", "conversation", "episodic", "semantic")

    async def chat(self, user_msg: str, history: list[dict]) -> str:
        recalled = self.memory.recall(user_msg, k=3)
        ctx = "\n".join(f"- [{r.tier}] {r.content}" for r in recalled)
        messages = [*history, {"role": "user", "content":
                    (f"Relevant memory:\n{ctx}\n\n" if ctx else "") + user_msg}]
        reply = await self.think(messages)
        await self.remember(f"user said: {user_msg[:300]}", tier="conversation")
        return reply
