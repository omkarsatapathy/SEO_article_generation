import json
import logging
import inspect
from datetime import datetime, timezone
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.graph.state import ArticleGenerationState, QAResult
from app.graph.tools import get_llm
from app.graph.tools.seo_validator import seo_validator_tool
from config.config import cfg

logger = logging.getLogger(__name__)


def _get_max_iterations() -> int:
    return cfg.hyperparams.agent.qa_max_iterations


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
def score_calculator_tool(score: int, penalty: int = 0, bonus: int = 0) -> int:
    """Adjust a QA score with optional penalty/bonus; clamps between 0 and 100."""
    adjusted = score - penalty + bonus
    return max(0, min(100, adjusted))


def _build_qa_agent():
    return create_react_agent(
        model=get_llm(),
        tools=[
            _normalize_tool(seo_validator_tool, "seo_validator_tool"),
            _normalize_tool(score_calculator_tool, "score_calculator_tool"),
        ],
        prompt=cfg.prompts.agents.qa,
    )


def _extract_agent_payload(agent_result: Dict[str, Any]) -> Dict[str, Any]:
    messages = agent_result.get("messages") or []
    if not messages:
        raise ValueError("QA agent returned no messages")

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
        content = str(final_message)
    if not isinstance(content, str):
        content = str(content)

    return json.loads(content)


def _coerce_qa_result(raw: Any) -> QAResult:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    return QAResult.model_validate(raw or {})


def qa_node(state: ArticleGenerationState) -> dict:
    """Run the SEO quality validator via a ReAct agent and decide: pass or revise."""
    logger.info("───────────────────────────────────────────────────")
    logger.info("🔎 QA NODE — Starting (revision #%d)", state.get("revision_count", 0))

    try:
        agent = _build_qa_agent()

        article = state.get("article_draft") or ""
        metadata = state.get("seo_metadata")
        keywords = state.get("extracted_keywords") or []
        word_count = state.get("word_count") or 1500

        user_message = (
            f"Use seo_validator_tool to score the article. Article: {article}. "
            f"metadata_json: {json.dumps(metadata.model_dump() if metadata else {})}. "
            f"keywords_json: {json.dumps([k.model_dump() for k in keywords])}. "
            f"target_word_count: {word_count}. "
            "Return only JSON with qa_result: score, passed, issues, suggestions."
        )

        try:
            agent_result = agent.invoke(
                {"messages": [("user", user_message)]},
                config={"recursion_limit": _get_max_iterations()},
            )

            payload = _extract_agent_payload(agent_result)
            raw_result = payload.get("qa_result") or payload

            if isinstance(raw_result, dict) and not raw_result.get("score"):
                raw_result = payload

            result = _coerce_qa_result(raw_result)
        except Exception as agent_exc:
            logger.warning("   ⚠️  QA agent failed (%s). Using direct validator fallback.", agent_exc)
            result_json: str = seo_validator_tool.invoke(
                {
                    "article": article,
                    "metadata_json": json.dumps(metadata.model_dump() if metadata else {}),
                    "keywords_json": json.dumps([k.model_dump() for k in keywords]),
                    "target_word_count": word_count,
                }
            )
            result = QAResult.model_validate_json(result_json)

        logger.info(
            "   📈 SEO Score: %d / 100  (pass threshold: %d)",
            result.score, cfg.hyperparams.qa.pass_score,
        )
        if result.issues:
            for issue in result.issues:
                logger.info("      ⚠️  %s", issue)
        if result.suggestions:
            for sug in result.suggestions:
                logger.info("      💡 %s", sug)

        if result.passed:
            logger.info("   ✅ QA PASSED → moving to output")
            logger.info("───────────────────────────────────────────────────")
            return {
                "qa_result": result,
                "final_article": article,
                "status": "done",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        new_rev = state.get("revision_count", 0) + 1
        max_rev = cfg.hyperparams.pipeline.max_revisions
        if new_rev >= max_rev:
            logger.warning("   ⚠️  Max revisions reached (%d). Publishing best-effort.", new_rev)
            logger.info("───────────────────────────────────────────────────")
            return {
                "qa_result": result,
                "final_article": article,
                "revision_count": new_rev,
                "status": "done",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        logger.info("   🔄 QA FAILED — sending back to writer for revision #%d", new_rev)
        logger.info("───────────────────────────────────────────────────")
        return {
            "qa_result": result,
            "revision_count": new_rev,
            "status": "writing",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error("   ❌ QA NODE FAILED: %s", exc, exc_info=True)
        return {
            "errors": [f"qa_node error: {exc}"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
