"""Sync: pull from live systems -> Phase 4 ingestion (knowledge tier).

This is the bridge ATIQ taught us to build: tickets lead with description +
comments; PR/repo signals are secondary context, ingested separately.
"""
import asyncio

from manas.kernel.registry import tools
from manas.knowledge.engine import ingest_ticket
from manas.memory import get_store
from manas.memory.store import Record
import hashlib


def _kid(source: str, text: str) -> str:
    return hashlib.blake2b(f"{source}#{text}".encode(), digest_size=6).hexdigest()


def _write_once(source: str, content: str, kind: str, importance: float = 0.5) -> bool:
    store = get_store()
    rid = _kid(source, content)
    if any(r.id == rid for r in store.all_active("knowledge")):
        return False
    store.write(Record(id=rid, tier="knowledge", source=source,
                       importance=importance, links=[f"kind:{kind}"],
                       content=content))
    return True


def sync_jira(key: str) -> str:
    ticket = asyncio.run(tools.get("jira_fetch")()(key=key))
    return ingest_ticket(ticket)


def sync_github(full_name: str, prs: bool = True) -> dict:
    gh = tools.get("github_fetch")()
    repo = asyncio.run(gh(full_name=full_name, resource="repo"))
    report = {"repo": 0, "prs": 0}
    text = (f"[repo] {full_name}: {repo.get('description') or ''}\n"
            f"default_branch: {repo.get('default_branch')}  "
            f"language: {repo.get('language')}  stars: {repo.get('stargazers_count')}\n"
            f"topics: {', '.join(repo.get('topics', []))}")
    report["repo"] += _write_once(f"github:{full_name}", text, "repo")
    if prs:
        for pr in asyncio.run(gh(full_name=full_name, resource="prs")):
            body = (f"[pr] {full_name}#{pr['number']}: {pr['title']}\n"
                    f"author: {pr['user']['login']}  state: {pr['state']}\n"
                    f"{(pr.get('body') or '')[:1500]}")
            report["prs"] += _write_once(
                f"github:{full_name}#pr{pr['number']}", body, "pr", 0.55)
    return report
