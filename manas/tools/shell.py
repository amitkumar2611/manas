"""Shell tool — APPROVAL risk, jailed to workdir, timeout + output caps."""
import asyncio

from manas.kernel.config import settings
from manas.kernel.registry import tools


@tools.register("shell")
class ShellTool:
    risk_level = "APPROVAL"
    approval_reason = "executes a command on the host"

    async def __call__(self, command: str, timeout: int = 60) -> dict:
        proc = await asyncio.create_subprocess_shell(
            command, cwd=settings.workdir_jail,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"rc": -1, "stdout": "", "stderr": f"timeout after {timeout}s"}
        return {"rc": proc.returncode,
                "stdout": out.decode()[:20000], "stderr": err.decode()[:20000]}
