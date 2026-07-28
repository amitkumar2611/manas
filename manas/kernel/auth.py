"""RBAC: users, roles, and risk ceilings (prompts/30_security.md).

Single-user mode = implicit admin, but the permission check STILL RUNS —
that rule is constitutional, so multi-user is a data change, not a code change.
"""
from dataclasses import dataclass, field

from manas.kernel.errors import ToolDenied

ROLE_CEILING = {"viewer": "SAFE", "operator": "REVIEW", "admin": "APPROVAL"}
_RISK = {"SAFE": 0, "REVIEW": 1, "APPROVAL": 2}


@dataclass
class User:
    name: str
    roles: tuple[str, ...] = ("admin",)
    memory_scopes: tuple[str, ...] = ("personal", "enterprise")

    @property
    def ceiling(self) -> str:
        best = "SAFE"
        for r in self.roles:
            c = ROLE_CEILING.get(r, "SAFE")
            if _RISK[c] > _RISK[best]:
                best = c
        return best

    def check_tool(self, tool_name: str, risk: str) -> None:
        if _RISK[risk] > _RISK[self.ceiling]:
            raise ToolDenied(
                f"user '{self.name}' (roles={list(self.roles)}, "
                f"ceiling={self.ceiling}) may not run {risk}-level "
                f"tool '{tool_name}'")

    def check_memory_scope(self, scope: str) -> None:
        if scope not in self.memory_scopes:
            raise ToolDenied(f"user '{self.name}' has no grant for "
                             f"memory scope '{scope}'")


SYSTEM_USER = User(name="local", roles=("admin",))
