"""ToolGate: the single choke point between agents and the real world.

Implements prompts/30_security.md — denylist, jail, approvals, audit.
"""
import time
from typing import Any, Callable

from manas.kernel import audit
from manas.kernel.errors import ApprovalRequired, ToolDenied
from manas.kernel.metrics import TOOL_LAT, TOOL_RUNS
from manas.kernel.registry import tools
from manas.kernel.trace import span

DENYLIST = ("rm -rf /", "mkfs", ":(){", "curl | sh", "curl|sh", "> /dev/sda")
RISK = {"SAFE": 0, "REVIEW": 1, "APPROVAL": 2}


class ToolGate:
    def __init__(self, approver: Callable[[str, str], bool] | None = None) -> None:
        # approver(action, reason) -> bool. None = deny anything needing approval.
        self.approver = approver

    async def run(self, agent: str, tool_name: str, **kwargs: Any) -> Any:
        tool = tools.get(tool_name)
        risk: str = getattr(tool, "risk_level", "APPROVAL")

        blob = " ".join(str(v) for v in kwargs.values())
        if any(bad in blob for bad in DENYLIST):
            audit.record(agent, tool_name, kwargs, risk, None, "DENIED")
            TOOL_RUNS.inc(tool=tool_name, status="denied")
            raise ToolDenied(f"denylist match in args for {tool_name}")

        approved_by = None
        if RISK[risk] >= RISK["APPROVAL"]:
            reason = getattr(tool, "approval_reason", "irreversible action")
            if not self.approver:
                audit.record(agent, tool_name, kwargs, risk, None, "BLOCKED")
                raise ApprovalRequired(tool_name, reason)
            if not self.approver(tool_name, reason):
                audit.record(agent, tool_name, kwargs, risk, None, "REJECTED")
                raise ToolDenied(f"human rejected {tool_name}")
            approved_by = "human"

        t0 = time.time()
        try:
            with span("tool.run", tool=tool_name, agent=agent, risk=risk):
                result = await tool()(**kwargs)
            audit.record(agent, tool_name, kwargs, risk, approved_by, "OK")
            TOOL_RUNS.inc(tool=tool_name, status="ok")
            return result
        except Exception:
            audit.record(agent, tool_name, kwargs, risk, approved_by, "ERROR")
            TOOL_RUNS.inc(tool=tool_name, status="error")
            raise
        finally:
            TOOL_LAT.observe(time.time() - t0, tool=tool_name)
