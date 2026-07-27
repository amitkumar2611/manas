"""Screen understanding: OCR is core (verifiable anywhere); capture is
display-dependent and optional."""
from pathlib import Path

from manas.kernel.errors import ManasError
from manas.kernel.registry import tools


@tools.register("ocr_image")
class OcrImage:
    """Extract text from an image file (Tesseract)."""
    risk_level = "SAFE"

    async def __call__(self, path: str, lang: str = "eng") -> dict:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as e:
            raise ManasError("OCR needs: pip install pillow pytesseract "
                             "+ apt install tesseract-ocr") from e
        p = Path(path).expanduser()
        if not p.exists():
            raise ManasError(f"no such image: {p}")
        text = pytesseract.image_to_string(Image.open(p), lang=lang)
        return {"path": str(p), "chars": len(text), "text": text.strip()}


@tools.register("screenshot")
class Screenshot:
    """Capture the screen to a PNG. Requires a display (laptop/desktop)."""
    risk_level = "SAFE"

    async def __call__(self, out: str = "screen.png", monitor: int = 1) -> dict:
        try:
            import mss  # optional: pip install mss
        except ImportError as e:
            raise ManasError("screenshot needs: pip install mss") from e
        try:
            with mss.mss() as s:
                s.shot(mon=monitor, output=out)
        except Exception as e:  # headless host: honest failure, no fake image
            raise ManasError(f"no display available for capture: {e}") from e
        return {"saved": out}


async def read_screen(gate, agent: str = "assistant") -> dict:
    """Convenience pipeline: screenshot -> OCR (the JARVIS 'look at my screen')."""
    shot = await gate.run(agent, "screenshot", out="/tmp/manas-screen.png")
    return await gate.run(agent, "ocr_image", path=shot["saved"])
