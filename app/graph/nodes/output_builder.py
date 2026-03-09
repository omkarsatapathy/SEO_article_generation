import logging
from datetime import datetime, timezone

from app.graph.state import ArticleGenerationState

logger = logging.getLogger(__name__)


def output_builder_node(state: ArticleGenerationState) -> dict:
    """Final assembly: package the best available article as the result."""
    logger.info("───────────────────────────────────────────────────")
    logger.info("📦 OUTPUT BUILDER NODE — Assembling final result")

    final = state.get("final_article") or state.get("article_draft") or ""
    word_count = len(final.split()) if final else 0

    logger.info("   Final article: %d words", word_count)
    logger.info("   SEO metadata:  %s", "present" if state.get("seo_metadata") else "missing")
    logger.info("   Internal links: %d", len(state.get("internal_links") or []))
    logger.info("   External refs:  %d", len(state.get("external_references") or []))

    qa = state.get("qa_result")
    if qa:
        logger.info("   QA score:       %d / 100", qa.score)

    logger.info("═══════════════════════════════════════════════════")
    logger.info("🏁 PIPELINE COMPLETE — Job ID: %s", state.get("job_id"))
    logger.info("   Status: done")
    logger.info("   View result: GET /jobs/%s/result", state.get("job_id"))
    logger.info("═══════════════════════════════════════════════════")

    return {
        "final_article": final,
        "status": "done",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
