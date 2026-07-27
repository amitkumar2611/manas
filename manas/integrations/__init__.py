"""Integration layer: external systems as ToolGate-guarded tools.

Risk policy (prompts/30_security.md): reads are SAFE, anything that leaves
the machine or mutates an external system is APPROVAL. No exceptions.
"""
from manas.integrations import email_i, github, jira, slack, testrail  # noqa: F401
