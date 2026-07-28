"""Env-driven configuration. Every default works offline (local-first)."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MANAS_", env_file=".env",
                                      extra="ignore")

    home: Path = Path.home() / ".manas"          # state, memory, audit
    provider: str = "echo"                        # echo|anthropic|copilot|ollama
    memory_backend: str = "sqlite"                # sqlite (Phase 2) | jsonl (Phase 1)
    embedder: str = "hash"                        # hash (offline) | ollama
    embed_model: str = "nomic-embed-text"
    model: str = ""                               # provider-specific model id
    anthropic_api_key: str = ""
    github_com_token: str = ""                    # Copilot API (ATIQ convention)
    ollama_url: str = "http://localhost:11434"
    approval_mode: str = "ask"                    # ask|deny (never "auto")
    workdir_jail: Path = Path.cwd()
    # -- Phase 5 integrations (all optional; tools error clearly if unset) --
    github_api: str = "https://api.github.com"    # GHE: https://github.hpe.com/api/v3
    github_token: str = ""                        # ATIQ convention: Enterprise reads
    jira_url: str = ""
    jira_email: str = ""
    jira_token: str = ""
    testrail_url: str = ""
    testrail_user: str = ""
    testrail_key: str = ""
    slack_webhook: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""
    # -- Phase 6 perception --
    wake_word: str = "manas"
    stt_model: str = "base"                       # faster-whisper model size
    calendar_dir: str = ""                        # blank -> ~/.manas/calendar
    # -- Phase 9 provider hardening --
    provider_fallbacks: str = ""                  # e.g. "ollama,echo"
    routes: str = ""                              # e.g. "critic=ollama:llama3.1"
    cost_per_mtok: str = "anthropic=3:15,copilot=0:0,ollama=0:0,echo=0:0"
    # -- Phase 11 RBAC + scoped stores --
    personal_key: str = ""                        # blank -> autogen ~/.manas/keys
    enterprise_key: str = ""
    # -- Phase 14 edge/IoT --
    mqtt_broker: str = "localhost:1883"
    mqtt_user: str = ""
    mqtt_pass: str = ""

    def ensure_dirs(self) -> None:
        for sub in ("memory", "audit", "plans"):
            (self.home / sub).mkdir(parents=True, exist_ok=True)


settings = Settings()
