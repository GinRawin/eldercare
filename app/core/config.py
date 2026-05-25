from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+psycopg2://eldercare:eldercare@localhost:5432/eldercare"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False


settings = Settings()
