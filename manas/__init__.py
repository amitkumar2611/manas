"""MANAS — Modular Autonomous Neural Agent System.

An AI Operating System kernel: agents, tools, memory, and providers
composed over a typed event bus with human-in-the-loop safety gates.

Importing `manas` bootstraps the component registries (open/closed:
new components self-register; kernel code never changes).
"""
__version__ = "0.7.0"

from manas import agents, integrations, memory, perception, providers, tools  # noqa: E402,F401  (registry bootstrap)
