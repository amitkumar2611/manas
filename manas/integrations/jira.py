"""Jira adapter: issue reads are SAFE; comments are APPROVAL."""
from manas.kernel.config import settings
from manas.kernel.errors import ProviderError
from manas.kernel.registry import tools
from manas.integrations.http import request


def _auth():
    if not (settings.jira_url and settings.jira_email and settings.jira_token):
        raise ProviderError("set MANAS_JIRA_URL / _JIRA_EMAIL / _JIRA_TOKEN")
    return (settings.jira_email, settings.jira_token)


@tools.register("jira_fetch")
class JiraFetch:
    risk_level = "SAFE"

    async def __call__(self, key: str) -> dict:
        d = request("GET",
                    f"{settings.jira_url}/rest/api/2/issue/{key}"
                    "?fields=summary,description,status,comment",
                    auth=_auth())
        f = d.get("fields", {})
        return {"key": d.get("key", key),
                "summary": f.get("summary", ""),
                "description": f.get("description") or "",
                "status": (f.get("status") or {}).get("name", ""),
                "comments": [c.get("body", "") for c in
                             (f.get("comment") or {}).get("comments", [])]}


@tools.register("jira_comment")
class JiraComment:
    risk_level = "APPROVAL"
    approval_reason = "posts a comment to a live Jira ticket"

    async def __call__(self, key: str, body: str) -> dict:
        return request("POST", f"{settings.jira_url}/rest/api/2/issue/{key}/comment",
                       auth=_auth(), json_body={"body": body})
