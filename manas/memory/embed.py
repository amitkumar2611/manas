"""Embedders for semantic recall. Local-first: the default needs no model,
no network, no download — deterministic char-n-gram feature hashing.
Swap to Ollama embeddings via MANAS_EMBEDDER=ollama once a model is pulled.
"""
import hashlib
import math
from array import array
from typing import Protocol

import httpx

from manas.kernel.config import settings

DIM = 256


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashEmbedder:
    """Feature-hashed character 3-grams, L2-normalized. Zero dependencies,
    fully offline, surprisingly effective for short memory records."""

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * DIM
        t = f"  {text.lower()}  "
        for i in range(len(t) - 2):
            h = int.from_bytes(hashlib.blake2b(
                t[i:i + 3].encode(), digest_size=4).digest(), "big")
            vec[h % DIM] += 1.0 if (h >> 31) & 1 else -1.0  # signed hashing
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OllamaEmbedder:
    """Real semantic embeddings from a local Ollama model."""

    def embed(self, text: str) -> list[float]:
        r = httpx.post(f"{settings.ollama_url}/api/embeddings",
                       json={"model": settings.embed_model, "prompt": text},
                       timeout=60)
        r.raise_for_status()
        return r.json()["embedding"]


def get_embedder() -> Embedder:
    return OllamaEmbedder() if settings.embedder == "ollama" else HashEmbedder()


def to_blob(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def from_blob(blob: bytes) -> list[float]:
    a = array("f"); a.frombytes(blob)
    return list(a)


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
