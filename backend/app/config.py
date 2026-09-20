from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://advisor:advisor@db:5432/advisor"
    cors_origins: list[str] = ["http://localhost:5173"]

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    advisor_model: str = "anthropic/claude-sonnet-5"


settings = Settings()
