"""Slack adapter (incoming webhook): any post leaves the machine -> APPROVAL."""
from manas.kernel.config import settings
from manas.kernel.errors import ProviderError
from manas.kernel.registry import tools
from manas.integrations.http import request


@tools.register("slack_post")
class SlackPost:
    risk_level = "APPROVAL"
    approval_reason = "sends a message to a Slack channel"

    async def __call__(self, text: str) -> dict:
        if not settings.slack_webhook:
            raise ProviderError("set MANAS_SLACK_WEBHOOK")
        request("POST", settings.slack_webhook, json_body={"text": text})
        return {"sent": True, "chars": len(text)}
