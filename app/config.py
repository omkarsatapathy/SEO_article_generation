from pydantic import ConfigDict
from pydantic_settings import BaseSettings

from config.config import cfg


class Settings(BaseSettings):
    """Runtime settings — secrets come from .env; defaults come from config/settings.yaml."""

    model_config = ConfigDict(env_file=".env")

    # Secrets — must be set in.env (no YAML default)
    OPENAI_API_KEY: str
    SERPAPI_KEY: str

    # Overridable via env; fall back to YAML defaults
    DATABASE_URL: str = cfg.settings.database.default_url
    LLM_MODEL: str = cfg.settings.llm.model
    WRITER_LLM_MODEL: str = cfg.settings.llm.writer_model
    MAX_RETRIES: int = cfg.hyperparams.pipeline.max_retries
    QA_PASS_SCORE: int = cfg.hyperparams.qa.pass_score


settings = Settings()
