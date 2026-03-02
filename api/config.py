from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "changeme"
    vault_path: str = "/vault"
    ollama_url: str = "http://ollama:11434"
    database_url: str = "sqlite+aiosqlite:////data/kb.db"
    chromadb_path: str = "/data/chroma"

    class Config:
        env_file = ".env"


settings = Settings()
