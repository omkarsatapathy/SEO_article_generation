import json
import logging
import inspect
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.graph.state import ArticleGenerationState
from app.graph.tools import get_llm
from config.config import cfg

logger = logging.getLogger(__name__)

# Resolved lazily from config so tests can override cfg before importing
_MAX_AGENT_ITERATIONS = None


def _get_max_iterations() -> int:
    global _MAX_AGENT_ITERATIONS
    if _MAX_AGENT_ITERATIONS is None:
        _MAX_AGENT_ITERATIONS = cfg.hyperparams.agent.orchestrator_max_iterations
    return _MAX_AGENT_ITERATIONS


def _normalize_tool(t, name: str):
    """Ensure tools are functions with a __name__, wrapping mocks when needed."""
    if inspect.isfunction(t) or inspect.ismethod(t) or inspect.isclass(t) or inspect.ismodule(t):
        if not getattr(t, "__name__", None):
            try:
                t.__name__ = name
            except Exception:
                pass
        if not getattr(t, "__doc__", None):
            try:
                t.__doc__ = "Wrapped tool"
            except Exception:
                pass
        return t

    # LangChain BaseTool / StructuredTool instances expose .invoke but are not callable
    if hasattr(t, "invoke"):
        if not getattr(t, "__name__", None):
            try:
                t.__name__ = getattr(t, "name", None) or name
            except Exception:
                pass
        if not getattr(t, "__doc__", None):
            try:
                t.__doc__ = getattr(t, "description", None) or "Wrapped tool"
            except Exception:
                pass
        return t

    def wrapper(*args, **kwargs):
        # Fallback for mocks; call underlying object if callable else return as-is
        if hasattr(t, "invoke"):
            return t.invoke(*args, **kwargs)
        if callable(t):
            return t(*args, **kwargs)
        return t

    wrapper.__name__ = name
    wrapper.__qualname__ = name
    wrapper.__doc__ = getattr(t, "__doc__", "Wrapped mock tool") or "Wrapped mock tool"
    return wrapper


@tool
def validate_input_tool(topic: str, word_count: Optional[int] = None, language: Optional[str] = None) -> Dict[str, Any]:
    """Validate and normalise the incoming request fields."""
    topic_clean = (topic or "").strip()
    if not topic_clean:
        raise ValueError("'topic' must be a non-empty string.")

    default_wc = cfg.hyperparams.pipeline.default_word_count
    default_lang = cfg.hyperparams.pipeline.default_language
    resolved_word_count = int(word_count) if word_count else default_wc
    resolved_language = (language or default_lang).strip() or default_lang

    return {
        "topic": topic_clean,
        "word_count": resolved_word_count,
        "language": resolved_language,
    }


@tool
def job_init_tool(topic: str, word_count: int, language: str) -> Dict[str, Any]:
    """Create job identifiers and timestamps."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "job_id": str(uuid4()),
        "topic": topic.strip(),
        "word_count": word_count,
        "language": language.strip(),
        "status": "researching",
        "retry_counts": {"research": 0, "outline": 0, "writer": 0, "qa": 0},
        "revision_count": 0,
        "created_at": now,
        "updated_at": now,
    }


def _build_orchestrator_agent():
    return create_react_agent(
        model=get_llm(),
        tools=[
            _normalize_tool(validate_input_tool, "validate_input_tool"),
            _normalize_tool(job_init_tool, "job_init_tool"),
        ],
        prompt=cfg.prompts.agents.orchestrator,
    )


def _extract_agent_payload(agent_result: Dict[str, Any]) -> Dict[str, Any]:
    messages = agent_result.get("messages") or []
    if not messages:
        raise ValueError("Orchestrator agent returned no messages")

    final_message = messages[-1]
    content = getattr(final_message, "content", final_message)
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        content = " ".join(
            fragment.get("text", "") if isinstance(fragment, dict) else str(fragment)
            for fragment in content
        )
    if isinstance(final_message, AIMessage) and not isinstance(content, str):
        content = final_message.pretty_print()
    if not isinstance(content, str):
        content = str(content)

    return json.loads(content)


def orchestrator_node(state: ArticleGenerationState) -> dict:
    """Validate inputs, set defaults, and initialise job metadata via a ReAct agent."""
    topic = (state.get("topic") or "").strip()
    if not topic:
        raise ValueError("'topic' must be a non-empty string.")

    agent = _build_orchestrator_agent()

    logger.info("═══════════════════════════════════════════════════")
    logger.info("🚀 PIPELINE STARTED")
    logger.info("   Topic:      %s", topic)
    logger.info("   Word count: %s", state.get("word_count") or cfg.hyperparams.pipeline.default_word_count)
    logger.info("   Language:   %s", state.get("language") or cfg.hyperparams.pipeline.default_language)

    user_message = (
        f"Validate inputs and initialise a new SEO article generation job. "
        f"Topic: {topic}. Word_count: {state.get('word_count')}. Language: {state.get('language')}. "
        "Return only JSON with keys: job_id, word_count, language, status, retry_counts, "
        "revision_count, created_at, updated_at. Use the tools to do the work."
    )

    try:
        agent_result = agent.invoke(
            {"messages": [("user", user_message)]},
            config={"recursion_limit": _get_max_iterations()},
        )
        payload = _extract_agent_payload(agent_result)
    except Exception as agent_exc:
        logger.warning("   ⚠️  Orchestrator agent failed (%s). Using deterministic fallback.", agent_exc)
        validated = validate_input_tool.invoke(
            {
                "topic": topic,
                "word_count": state.get("word_count"),
                "language": state.get("language"),
            }
        )
        payload = job_init_tool.invoke(validated)

    now = datetime.now(timezone.utc).isoformat()
    retry_counts = payload.get("retry_counts") or {"research": 0, "outline": 0, "writer": 0, "qa": 0}

    default_wc = cfg.hyperparams.pipeline.default_word_count
    default_lang = cfg.hyperparams.pipeline.default_language
    final_state = {
        "job_id": payload.get("job_id") or str(uuid4()),
        "word_count": payload.get("word_count") or state.get("word_count") or default_wc,
        "language": payload.get("language") or state.get("language") or default_lang,
        "status": payload.get("status") or "researching",
        "retry_counts": retry_counts,
        "revision_count": payload.get("revision_count", state.get("revision_count", 0)) or 0,
        "created_at": payload.get("created_at") or now,
        "updated_at": payload.get("updated_at") or now,
    }

    logger.info("   Job ID:     %s", final_state["job_id"])
    logger.info("═══════════════════════════════════════════════════")

    return final_state
