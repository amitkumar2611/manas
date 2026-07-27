"""Typed exceptions for MANAS. Never raise bare Exception in library code."""


class ManasError(Exception):
    """Base for all MANAS errors."""


class RegistryError(ManasError):
    """Component registration/lookup failure."""


class ProviderError(ManasError):
    """LLM provider failure (network, auth, bad response)."""


class ToolDenied(ManasError):
    """ToolGate refused execution (denylist / missing approval)."""


class ApprovalRequired(ManasError):
    """Action needs explicit human approval before it can run."""

    def __init__(self, action: str, reason: str) -> None:
        self.action, self.reason = action, reason
        super().__init__(f"APPROVAL REQUIRED: {action} — {reason}")
