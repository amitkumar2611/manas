"""GitHub adapter — works for github.com and GitHub Enterprise.

ATIQ convention preserved: MANAS_GITHUB_TOKEN authenticates the (Enterprise)
API at MANAS_GITHUB_API (e.g. https://github.hpe.com/api/v3), while
GITHUB_COM_TOKEN remains the Copilot LLM credential — two different tokens.
"""
from manas.kernel.config import settings
from manas.kernel.registry import tools
from manas.integrations.http import request


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        h["Authorization"] = f"Bearer {settings.github_token}"
    return h


@tools.register("github_fetch")
class GithubFetch:
    """Read repo metadata, PRs, or issues. resource: repo|prs|issues"""
    risk_level = "SAFE"

    async def __call__(self, full_name: str, resource: str = "repo",
                       state: str = "open", limit: int = 10) -> dict | list:
        base = f"{settings.github_api}/repos/{full_name}"
        if resource == "repo":
            return request("GET", base, headers=_headers())
        if resource in ("prs", "pulls"):
            return request("GET", f"{base}/pulls?state={state}&per_page={limit}",
                           headers=_headers())
        if resource == "issues":
            return request("GET", f"{base}/issues?state={state}&per_page={limit}",
                           headers=_headers())
        raise ValueError(f"unknown resource '{resource}'")
