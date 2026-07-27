"""Provider layer: pluggable LLM backends behind one interface."""
from manas.providers import anthropic_p, copilot_p, echo_p, ollama_p  # noqa: F401  (registration side effects)
from manas.providers.base import complete  # noqa: F401
