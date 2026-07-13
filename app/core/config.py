from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+psycopg2://eldercare:eldercare@localhost:5432/eldercare"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # 大模型客户端（OpenAI / 华为云兼容 Chat Completions）。
    # 留空即降级：safety-check 接口的别名扩展会退化为仅用原始输入名，不报错。
    LLM_BASE_URL: str = ""  # 例：https://api.openai.com/v1 或华为云兼容地址
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TIMEOUT: float = 10.0  # 秒

    # Dify 配置：由后端代理统一调用，前端不直接暴露 Key。
    DIFY_BASE_URL: str = ""
    DIFY_DIET_API_KEY: str = ""
    DIFY_MED_API_KEY: str = ""
    DIFY_TIMEOUT: float = 20.0


settings = Settings()
