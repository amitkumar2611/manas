"""Computer control: keyboard/mouse/app tools. APPROVAL, always.

Safety model beyond the ToolGate:
  1) Every action sequence supports dry_run=True -> returns the exact action
     plan WITHOUT touching the machine (audited as DRYRUN).
  2) The first live run of a given sequence requires a prior dry-run of the
     SAME sequence in the same process — replay-what-you-previewed.
Backend (pyautogui) is optional; headless hosts fail honestly.
"""
import hashlib
import json

from manas.kernel import audit
from manas.kernel.errors import ManasError
from manas.kernel.registry import tools

_previewed: set[str] = set()          # hashes of dry-run-approved sequences
VALID_OPS = {"move", "click", "type", "hotkey", "open_app"}


def _sig(steps: list[dict]) -> str:
    return hashlib.blake2b(json.dumps(steps, sort_keys=True).encode(),
                           digest_size=8).hexdigest()


def _plan(steps: list[dict]) -> list[str]:
    out = []
    for s in steps:
        op = s.get("op")
        if op not in VALID_OPS:
            raise ManasError(f"unknown desktop op '{op}'")
        if op == "move":
            out.append(f"move cursor to ({s['x']}, {s['y']})")
        elif op == "click":
            out.append(f"{s.get('button', 'left')}-click at "
                       f"({s.get('x', 'cur')}, {s.get('y', 'cur')})")
        elif op == "type":
            out.append(f"type {len(s['text'])} chars")   # never echo the text
        elif op == "hotkey":
            out.append(f"hotkey {'+'.join(s['keys'])}")
        elif op == "open_app":
            out.append(f"open application '{s['name']}'")
    return out


class _PyAutoGuiBackend:
    def __init__(self) -> None:
        try:
            import pyautogui  # optional: pip install pyautogui
        except Exception as e:  # ImportError or headless DISPLAY error
            raise ManasError("desktop control needs a display + "
                             "'pip install pyautogui'") from e
        pyautogui.FAILSAFE = True             # slam cursor to corner = abort
        self.g = pyautogui

    def do(self, s: dict) -> None:
        op = s["op"]
        if op == "move":
            self.g.moveTo(s["x"], s["y"], duration=0.2)
        elif op == "click":
            self.g.click(s.get("x"), s.get("y"), button=s.get("button", "left"))
        elif op == "type":
            self.g.typewrite(s["text"], interval=0.02)
        elif op == "hotkey":
            self.g.hotkey(*s["keys"])
        elif op == "open_app":
            import subprocess
            subprocess.Popen([s["name"]])


@tools.register("desktop_control")
class DesktopControl:
    risk_level = "APPROVAL"
    approval_reason = "controls your keyboard/mouse/applications"

    def __init__(self, backend=None) -> None:
        self._backend = backend               # injectable for tests

    async def __call__(self, steps: list[dict], dry_run: bool = True) -> dict:
        plan = _plan(steps)                   # validates ops either way
        sig = _sig(steps)
        if dry_run:
            _previewed.add(sig)
            audit.record("desktop", "desktop_control",
                         {"sig": sig, "n": len(steps)}, "APPROVAL",
                         None, "DRYRUN")
            return {"dry_run": True, "sig": sig, "plan": plan}
        if sig not in _previewed:
            raise ManasError("live run refused: dry-run this exact sequence "
                             "first (replay-what-you-previewed rule)")
        backend = self._backend or _PyAutoGuiBackend()
        for s in steps:
            backend.do(s)
        return {"dry_run": False, "sig": sig, "executed": plan}
