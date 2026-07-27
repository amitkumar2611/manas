"""Browser: read the web (SAFE) and act on it (APPROVAL).

browser_fetch: httpx + tag-stripping extraction — core, works everywhere.
browser_act:   Playwright session (goto/click/fill/screenshot) — optional
               backend, injectable driver so the command mapping is testable
               without a real browser.
"""
import re
from html.parser import HTMLParser

import httpx

from manas.kernel.errors import ManasError
from manas.kernel.registry import tools

_transport: httpx.BaseTransport | None = None      # tests inject


def set_transport(t: httpx.BaseTransport | None) -> None:
    global _transport
    _transport = t


class _TextExtract(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and data.strip():
            self.parts.append(data.strip())


@tools.register("browser_fetch")
class BrowserFetch:
    """Fetch a URL and return readable text + title."""
    risk_level = "SAFE"

    async def __call__(self, url: str, max_chars: int = 20000) -> dict:
        with httpx.Client(transport=_transport, follow_redirects=True,
                          timeout=30) as c:
            r = c.get(url, headers={"User-Agent": "manas/0.6"})
        if r.status_code >= 400:
            raise ManasError(f"GET {url} -> {r.status_code}")
        p = _TextExtract()
        p.feed(r.text)
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(p.parts))
        return {"url": url, "title": p.title.strip(),
                "text": text[:max_chars], "chars": len(text)}


class PlaywrightDriver:
    """Real backend. Optional: pip install playwright && playwright install chromium"""

    def __init__(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise ManasError("browser_act needs: pip install playwright "
                             "&& playwright install chromium") from e
        self._pw = sync_playwright().start()
        self.page = self._pw.chromium.launch(headless=True).new_page()

    def do(self, step: dict) -> str:
        op = step.get("op")
        if op == "goto":
            self.page.goto(step["url"]); return f"goto {step['url']}"
        if op == "click":
            self.page.click(step["selector"]); return f"click {step['selector']}"
        if op == "fill":
            self.page.fill(step["selector"], step["value"])
            return f"fill {step['selector']}"
        if op == "screenshot":
            self.page.screenshot(path=step.get("out", "page.png"))
            return f"screenshot -> {step.get('out', 'page.png')}"
        if op == "text":
            return self.page.inner_text(step.get("selector", "body"))[:5000]
        raise ManasError(f"unknown browser op '{op}'")


@tools.register("browser_act")
class BrowserAct:
    """Run a scripted sequence of browser steps. Acting on live pages can
    submit forms / click buttons -> APPROVAL, always."""
    risk_level = "APPROVAL"
    approval_reason = "drives a real browser (can click/submit on live sites)"

    def __init__(self, driver=None) -> None:
        self._driver = driver                      # injectable for tests

    async def __call__(self, steps: list[dict]) -> list[str]:
        drv = self._driver or PlaywrightDriver()
        return [drv.do(s) for s in steps]
