"""Agent layer. Agents talk only via the event bus; tools only via ToolGate."""
from manas.agents import (assistant, critic, curator, learning,
                          orchestrator, planner, researcher)  # noqa: F401
from manas.agents.base import BaseAgent  # noqa: F401
