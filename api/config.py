from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "changeme"
    vault_path: str = "/vault"
    ollama_url: str = "http://ollama:11434"
    database_url: str = "sqlite+aiosqlite:////data/kb.db"
    chromadb_path: str = "/data/chroma"
    mailgun_webhook_signing_key: str = ""
    ingest_email_whitelist: str = ""  # comma-separated emails, e.g. "you@example.com,other@example.com"
    app_version: str = "unknown"

    class Config:
        env_file = ".env"


settings = Settings()
