import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.graph.state import (
    ArticleGenerationState,
    ArticleDraft,
    ExternalReference,
    InternalLink,
    LinkingSuggestions,
    SeoMetadata,
)
from app.graph.tools.article_writer import article_writer_tool
from app.graph.tools.linking_tool import linking_tool
from app.graph.tools.metadata_generator import metadata_generator_tool
from config.config import cfg

logger = logging.getLogger(__name__)


def _coerce_links(raw: Dict[str, Any]) -> LinkingSuggestions:
    """Normalise various link payload shapes into a LinkingSuggestions model.

    Kept as a public helper for backwards compatibility and testing.
    """
    if isinstance(raw, LinkingSuggestions):
        return raw

    raw_internal = raw.get("internal_links") or raw.get("internal") or []
    raw_external = raw.get("external_references") or raw.get("external") or []

    internal = []
    for item in raw_internal:
        if isinstance(item, dict):
            internal.append(item)
        elif isinstance(item, InternalLink):
            internal.append(item)
        elif isinstance(item, str):
            internal.append({"anchor_text": item, "suggested_target_topic": item})

    external = []
    for item in raw_external:
        if isinstance(item, dict):
            external.append(item)
        elif isinstance(item, ExternalReference):
            external.append(item)
        elif isinstance(item, str):
            external.append({"source_url": item, "context": ""})

    return LinkingSuggestions.model_validate(
        {"internal": internal, "external": external}
    )


def writer_node(state: ArticleGenerationState) -> dict:
    """Write the full article, generate metadata, and suggest links via sequential tool calls."""
    revision = state.get("revision_count", 0)
    logger.info("-" * 60)
    logger.info("="*60)
    logger.info("#"*60)
    logger.info("✍️  WRITER NODE — Starting (revision #%d)", revision)
    print("State at this point:")
    print(json.dumps(dict(state), indent=2, default=str))

    try:
        outline_json = json.dumps([s.model_dump() for s in (state.get("outline") or [])])
        keywords_json = json.dumps([k.model_dump() for k in (state.get("extracted_keywords") or [])])
        themes_json = json.dumps(state.get("common_themes") or [])
        faq_json = json.dumps(state.get("faq_questions") or [])
        serp_results_json = json.dumps([s.model_dump() for s in (state.get("serp_results") or [])])
        competitor_structures_json = json.dumps([c.model_dump() for c in (state.get("competitor_structures") or [])])
        language: str = state.get("language") or cfg.hyperparams.pipeline.default_language
        target_wc = state.get("word_count") or cfg.hyperparams.pipeline.default_word_count

        extracted_keywords = state.get("extracted_keywords") or []
        primary_kw = next(
            (k.word for k in extracted_keywords if k.is_primary),
            state.get("topic", "topic"),
        )

        # ── Build QA feedback string (first-class, not buried in themes) ──
        qa_feedback = ""
        qa_result = state.get("qa_result")
        if qa_result and not qa_result.passed:
            issues_str = "\n".join(f"- {i}" for i in qa_result.issues)
            suggestions_str = "\n".join(f"- {s}" for s in qa_result.suggestions)
            qa_feedback = (
                f"REVISION #{revision} — fix ALL of these:\n"
                f"Issues:\n{issues_str}\n"
                f"Suggestions:\n{suggestions_str}"
            )
            logger.info(
                "   📋 QA feedback: %d issues, %d suggestions",
                len(qa_result.issues),
                len(qa_result.suggestions),
            )

        # ── Step 1: Generate article (section-by-section inside the tool) ──
        logger.info("   📝 Step 1/3: Generating article…")
        draft_json = article_writer_tool.invoke(
            {
                "outline_json": outline_json,
                "keywords_json": keywords_json,
                "themes_json": themes_json,
                "language": language,
                "faq_questions_json": faq_json,
                "target_word_count": target_wc,
                "qa_feedback": qa_feedback,
                "serp_results_json": serp_results_json,
                "competitor_structures_json": competitor_structures_json,
            }
        )
        draft = ArticleDraft.model_validate_json(draft_json)
        article_content = draft.content
        logger.info(
            "   ✅ Article: %d words, %d characters",
            len(article_content.split()), len(article_content),
        )

        # ── Step 2: Generate SEO metadata ─────────────────────────────────
        logger.info("   📝 Step 2/3: Generating metadata…")
        meta_json = metadata_generator_tool.invoke(
            {"article_content": article_content, "primary_keyword": primary_kw}
        )
        metadata = SeoMetadata.model_validate_json(meta_json)
        logger.info(
            "   ✅ Metadata: title='%s' (%d chars), desc (%d chars)",
            metadata.title_tag,
            len(metadata.title_tag),
            len(metadata.meta_description),
        )

        # ── Step 3: Generate link suggestions ─────────────────────────────
        logger.info("   📝 Step 3/3: Generating links…")
        link_json = linking_tool.invoke(
            {"outline_json": outline_json, "themes_json": themes_json}
        )
        links = LinkingSuggestions.model_validate_json(link_json)
        logger.info(
            "   ✅ Links: %d internal, %d external",
            len(links.internal),
            len(links.external),
        )

        logger.info("✍️  WRITER NODE — Complete → status: qa")
        logger.info("───────────────────────────────────────────────────")

        return {
            "article_draft": article_content,
            "seo_metadata": metadata,
            "internal_links": links.internal,
            "external_references": links.external,
            "status": "qa",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error("   ❌ WRITER NODE FAILED: %s", exc, exc_info=True)
        retry_counts = dict(state.get("retry_counts") or {})
        retry_counts["writer"] = retry_counts.get("writer", 0) + 1
        logger.info(
            "   🔄 Retry count: %d / %d",
            retry_counts["writer"],
            cfg.hyperparams.pipeline.max_retries,
        )
        return {
            "errors": [f"writer_node error: {exc}"],
            "retry_counts": retry_counts,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
