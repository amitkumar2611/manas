"""Knowledge engine: ingest external corpora into the knowledge memory tier.

Sources -> chunks -> embedded records, per prompts/40_memory.md: every source
indexed, embedded, categorised, linked, searchable — and idempotent, so
re-ingesting an unchanged corpus writes nothing.
"""
from manas.knowledge.engine import ingest_path, ingest_ticket  # noqa: F401
