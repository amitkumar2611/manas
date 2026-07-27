"""TestRail adapter: case/run reads are SAFE; posting results is APPROVAL."""
from manas.kernel.config import settings
from manas.kernel.errors import ProviderError
from manas.kernel.registry import tools
from manas.integrations.http import request


def _auth():
    if not (settings.testrail_url and settings.testrail_user
            and settings.testrail_key):
        raise ProviderError("set MANAS_TESTRAIL_URL / _TESTRAIL_USER / _TESTRAIL_KEY")
    return (settings.testrail_user, settings.testrail_key)


@tools.register("testrail_fetch")
class TestrailFetch:
    """resource: cases (needs project_id[, suite_id]) | run (needs run_id)"""
    risk_level = "SAFE"

    async def __call__(self, resource: str, project_id: int | None = None,
                       suite_id: int | None = None,
                       run_id: int | None = None) -> dict | list:
        api = f"{settings.testrail_url}/index.php?/api/v2"
        if resource == "cases":
            url = f"{api}/get_cases/{project_id}"
            if suite_id:
                url += f"&suite_id={suite_id}"
            return request("GET", url, auth=_auth())
        if resource == "run":
            return request("GET", f"{api}/get_run/{run_id}", auth=_auth())
        raise ValueError(f"unknown resource '{resource}'")


@tools.register("testrail_add_result")
class TestrailAddResult:
    risk_level = "APPROVAL"
    approval_reason = "writes a test result into a live TestRail run"

    async def __call__(self, run_id: int, case_id: int, status_id: int,
                       comment: str = "") -> dict:
        return request("POST",
                       f"{settings.testrail_url}/index.php?/api/v2/"
                       f"add_result_for_case/{run_id}/{case_id}",
                       auth=_auth(),
                       json_body={"status_id": status_id, "comment": comment})
