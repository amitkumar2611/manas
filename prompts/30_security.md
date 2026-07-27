# MANAS — Security (Layer 30)

## SECRETS
- Secrets enter only via env/keyring. Never logged, never echoed, never in
  tracebacks (kernel scrubs them). Never committed.

## EXECUTION SANDBOX
- Shell/Python execution runs through the ToolGate with:
  - command allowlist + denylist (rm -rf /, curl|sh, fork bombs, etc.)
  - working-directory jail
  - timeout + output caps
  - dry-run mode available for every destructive tool

## APPROVAL GATES (risk_level = APPROVAL, human must confirm)
- Deleting or overwriting user data
- Running shell commands outside the jail
- Sending anything externally (email, Slack, API writes)
- Deployments, purchases, credential changes

## AUDIT
- Every tool invocation appends an immutable audit record:
  {ts, agent, tool, args_hash, risk, approved_by, result_status}

## POSTURE
- RBAC-ready from day one (single-user mode = implicit admin, but the
  permission check still runs). Principle of least privilege everywhere.
