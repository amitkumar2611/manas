"""File tools — read is SAFE, write is REVIEW (jailed to workdir)."""
from pathlib import Path

from manas.kernel.config import settings
from manas.kernel.errors import ToolDenied
from manas.kernel.registry import tools


def _jailed(path: str) -> Path:
    p = (settings.workdir_jail / path).resolve()
    if not str(p).startswith(str(settings.workdir_jail.resolve())):
        raise ToolDenied(f"path escapes jail: {path}")
    return p


@tools.register("read_file")
class ReadFile:
    risk_level = "SAFE"

    async def __call__(self, path: str, max_chars: int = 50000) -> str:
        return _jailed(path).read_text()[:max_chars]


@tools.register("write_file")
class WriteFile:
    risk_level = "REVIEW"

    async def __call__(self, path: str, content: str) -> str:
        p = _jailed(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {len(content)} chars to {p}"
