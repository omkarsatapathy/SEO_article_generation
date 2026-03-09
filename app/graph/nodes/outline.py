import json
import logging
import inspect
from datetime import datetime, timezone
from typing import Any, Dict, List

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.graph.state import ArticleGenerationState, OutlineOutput
from app.graph.tools import get_llm
from app.graph.tools.outline_builder import outline_builder_tool
from config.config import cfg

logger = logging.getLogger(__name__)


def _get_max_iterations() -> int:
    return cfg.hyperparams.agent.outline_max_iterations


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
def keyword_mapper_tool(outline_json: str, keywords_json: str) -> str:
    """Map keywords to outline sections; returns a JSON list of sections with keywords."""
    try:
        outline = json.loads(outline_json)
        keywords = json.loads(keywords_json)
        keyword_words = [k.get("word") for k in keywords if isinstance(k, dict)]
        for section in outline:
            current = section.get("keywords") or []
            section["keywords"] = list(dict.fromkeys(current + keyword_words))
        return json.dumps(outline)
    except Exception:
        return outline_json


def _build_outline_agent():
    return create_react_agent(
        model=get_llm(),
        tools=[
            _normalize_tool(outline_builder_tool, "outline_builder_tool"),
            _normalize_tool(keyword_mapper_tool, "keyword_mapper_tool"),
        ],
        prompt=cfg.prompts.agents.outline,
    )


def _extract_agent_payload(agent_result: Dict[str, Any]) -> Dict[str, Any]:
    messages = agent_result.get("messages") or []
    if not messages:
        raise ValueError("Outline agent returned no messages")

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


def _coerce_outline(payload: Dict[str, Any]) -> OutlineOutput:
    sections = payload.get("outline") or payload.get("sections") or []
    return OutlineOutput.model_validate({"sections": sections})


def _validate_and_fix_outline(
    sections: List[Any],
    target_word_count: int,
) -> List[Any]:
    """Ensure outline word_targets are sane and sum to the target."""
    hp = cfg.hyperparams.outline
    h2_sections = [s for s in sections if s.level == "H2"]

    if len(h2_sections) < hp.min_h2_sections:
        logger.warning(
            "   ⚠️  Outline has only %d H2 sections (need ≥ %d). Outline may be thin.",
            len(h2_sections), hp.min_h2_sections,
        )

    # Enforce minimum per-H2
    for s in h2_sections:
        if s.word_target < hp.min_h2_word_target:
            s.word_target = hp.min_h2_word_target

    # Check total allocation
    total_allocated = sum(s.word_target for s in sections if s.level in ("H2", "H3"))
    lower = int(target_word_count * hp.word_allocation_lower_bound)
    if total_allocated < lower and h2_sections:
        deficit = target_word_count - total_allocated
        per_h2 = deficit // len(h2_sections)
        remainder = deficit % len(h2_sections)
        for i, s in enumerate(h2_sections):
            s.word_target += per_h2 + (1 if i < remainder else 0)
        logger.info(
            "   🔧 Redistributed %d words across %d H2s (was %d, now %d)",
            deficit, len(h2_sections), total_allocated, target_word_count,
        )

    return sections


def outline_node(state: ArticleGenerationState) -> dict:
    """Build a structured SEO outline from extracted themes and keywords via a ReAct agent."""
    logger.info("───────────────────────────────────────────────────")
    logger.info("📝 OUTLINE NODE — Starting")

    try:
        agent = _build_outline_agent()

        themes_json = json.dumps(state.get("common_themes") or [])
        keywords_json = json.dumps([k.model_dump() for k in (state.get("extracted_keywords") or [])])
        word_count: int = state.get("word_count") or cfg.hyperparams.pipeline.default_word_count

        logger.info("   Themes: %s", state.get("common_themes"))
        logger.info("   Target words: %d", word_count)

        user_message = (
            f"Use the tools to produce the best outline. Themes_json: {themes_json}. "
            f"Keywords_json: {keywords_json}. Word_count: {word_count}. "
            "Call outline_builder_tool with those values. If helpful, run keyword_mapper_tool to enrich keywords. "
            "Return only JSON with key 'outline' as a list of sections."
        )

        try:
            agent_result = agent.invoke(
                {"messages": [("user", user_message)]},
                config={"recursion_limit": _get_max_iterations()},
            )
            payload = _extract_agent_payload(agent_result)
            output = _coerce_outline(payload)
        except Exception as agent_exc:
            logger.warning("   ⚠️  Outline agent failed (%s). Using direct outline builder.", agent_exc)
            outline_json = outline_builder_tool.invoke(
                {
                    "themes_json": themes_json,
                    "keywords_json": keywords_json,
                    "word_count": word_count,
                }
            )
            output = OutlineOutput.model_validate_json(outline_json)

        h1s = [s for s in output.sections if s.level == "H1"]
        h2s = [s for s in output.sections if s.level == "H2"]
        h3s = [s for s in output.sections if s.level == "H3"]

        # Validate / fix word targets before passing to writer
        output.sections = _validate_and_fix_outline(output.sections, word_count)

        logger.info("   ✅ Outline built: %d H1, %d H2, %d H3 sections", len(h1s), len(h2s), len(h3s))
        for s in output.sections:
            logger.info("      %s %s (%d words)", s.level, s.heading, s.word_target)
        logger.info("📝 OUTLINE NODE — Complete → status: writing")
        logger.info("───────────────────────────────────────────────────")

        return {
            "outline": output.sections,
            "status": "writing",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error("   ❌ OUTLINE NODE FAILED: %s", exc)
        retry_counts = dict(state.get("retry_counts") or {})
        retry_counts["outline"] = retry_counts.get("outline", 0) + 1
        logger.info("   🔄 Retry count: %d / 3", retry_counts["outline"])
        return {
            "errors": [f"outline_node error: {exc}"],
            "retry_counts": retry_counts,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
