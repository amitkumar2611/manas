"""Ingestors by file type. Open/closed: register an extension, never edit core."""
from pathlib import Path
from typing import Callable

from manas.kernel.errors import ManasError

Reader = Callable[[Path], str]
_readers: dict[str, tuple[Reader, str]] = {}       # ext -> (reader, kind)

CODE_EXT = (".py", ".sh", ".yaml", ".yml", ".toml", ".json", ".js", ".ts",
            ".go", ".rs", ".java", ".c", ".cpp", ".h", ".sql", ".cfg", ".ini")
DOC_EXT = (".md", ".txt", ".rst", ".csv", ".log")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             "dist", "build", ".pytest_cache", ".idea", ".vscode"}
MAX_FILE_BYTES = 2_000_000


def register(ext: str, kind: str):
    def deco(fn: Reader) -> Reader:
        _readers[ext] = (fn, kind)
        return fn
    return deco


def _read_text(p: Path) -> str:
    return p.read_text(errors="replace")


for _e in CODE_EXT:
    _readers[_e] = (_read_text, "code")
for _e in DOC_EXT:
    _readers[_e] = (_read_text, "doc")


@register(".pdf", "doc")
def _read_pdf(p: Path) -> str:
    try:
        from pypdf import PdfReader  # optional dep: pip install pypdf
    except ImportError as e:
        raise ManasError("PDF ingestion needs 'pip install pypdf'") from e
    return "\n\n".join(pg.extract_text() or "" for pg in PdfReader(p).pages)


def read(path: Path) -> tuple[str, str] | None:
    """Returns (text, kind) or None if unsupported/oversized."""
    entry = _readers.get(path.suffix.lower())
    if not entry or path.stat().st_size > MAX_FILE_BYTES:
        return None
    reader, kind = entry
    return reader(path), kind


def walk(root: Path):
    """Yield ingestable files, skipping VCS/build/binary junk."""
    for p in sorted(root.rglob("*")):
        if p.is_file() and not (SKIP_DIRS & set(p.parts)):
            yield p
