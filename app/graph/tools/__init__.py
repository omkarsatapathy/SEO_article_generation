from langchain_openai import ChatOpenAI

from app.config import settings


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(model=settings.LLM_MODEL, temperature=0.7, api_key=settings.OPENAI_API_KEY)


def get_writer_llm() -> ChatOpenAI:
    """Returns the dedicated LLM for the WriterAgent (gpt-4.1 by default)."""
    return ChatOpenAI(model=settings.WRITER_LLM_MODEL, temperature=0.4, api_key=settings.OPENAI_API_KEY, max_tokens=16000)
