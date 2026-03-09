from langchain_openai import ChatOpenAI

from app.config import settings
from config.config import cfg


def get_llm() -> ChatOpenAI:
    s = cfg.settings.llm
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=s.temperature,
        api_key=settings.OPENAI_API_KEY,
    )


def get_writer_llm() -> ChatOpenAI:
    """Returns the dedicated LLM for the WriterAgent."""
    s = cfg.settings.llm
    return ChatOpenAI(
        model=settings.WRITER_LLM_MODEL,
        temperature=s.writer_temperature,
        api_key=settings.OPENAI_API_KEY,
        max_tokens=s.writer_max_tokens,
    )
