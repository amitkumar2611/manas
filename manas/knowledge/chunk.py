"""Chunking: split documents into overlapping, embedding-sized pieces."""
from dataclasses import dataclass

CHUNK_CHARS = 1200
OVERLAP = 150


@dataclass
class Chunk:
    text: str
    source: str          # file path / ticket key
    kind: str            # code | doc | ticket
    index: int


def split(text: str, source: str, kind: str) -> list[Chunk]:
    """Prefer paragraph/blank-line boundaries; hard-split oversized blocks."""
    out: list[Chunk] = []
    buf = ""
    for para in text.split("\n\n"):
        if len(buf) + len(para) + 2 > CHUNK_CHARS and buf:
            out.append(buf)
            buf = buf[-OVERLAP:] + "\n" + para        # keep overlap for context
        else:
            buf = f"{buf}\n\n{para}" if buf else para
        while len(buf) > CHUNK_CHARS * 2:              # pathological long block
            out.append(buf[:CHUNK_CHARS]); buf = buf[CHUNK_CHARS - OVERLAP:]
    if buf.strip():
        out.append(buf)
    return [Chunk(text=c.strip(), source=source, kind=kind, index=i)
            for i, c in enumerate(out) if c.strip()]
