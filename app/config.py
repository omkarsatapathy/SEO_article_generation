from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    OPENAI_API_KEY: str
    SERPAPI_KEY: str
    DATABASE_URL: str = "postgresql://user:pass@localhost:5432/seo_agent"
    LLM_MODEL: str = "gpt-5-mini"
    WRITER_LLM_MODEL: str = "gpt-4.1"
    MAX_RETRIES: int = 3
    QA_PASS_SCORE: int = 80


settings = Settings()
