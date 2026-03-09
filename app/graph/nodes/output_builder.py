import logging
from datetime import datetime, timezone
from typing import List

from app.graph.state import ArticleGenerationState

logger = logging.getLogger(__name__)

_MAX_REFERENCE_LINKS = 5


def _get_attr(obj, key: str, default=None):
    """Retrieve a field from either a Pydantic model or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _build_references_section(
    external_references: list,
    serp_results: list,
    max_links: int = _MAX_REFERENCE_LINKS,
) -> str:
    """
    Build a Markdown References section with up to *max_links* hyperlinks.

    Priority order:
      1. external_references  – authoritative picks from the linking/research agent
      2. serp_results         – real SERP URLs, taken in rank order to fill any gap
    """
    seen_urls: set = set()
    refs: List[dict] = []

    # 1. Authoritative external references produced by the research/linking agent
    for ref in (external_references or []):
        url = _get_attr(ref, "source_url")
        context = _get_attr(ref, "context", "") or ""
        if url and url not in seen_urls:
            seen_urls.add(url)
            refs.append({"url": url, "label": context or url})
        if len(refs) >= max_links:
            break

    # 2. Top SERP results (sorted by rank) to reach max_links
    sorted_serp = sorted(
        serp_results or [],
        key=lambda r: _get_attr(r, "rank", 999),
    )
    for result in sorted_serp:
        if len(refs) >= max_links:
            break
        url = _get_attr(result, "url")
        title = _get_attr(result, "title") or url
        if url and url not in seen_urls:
            seen_urls.add(url)
            refs.append({"url": url, "label": title})

    if not refs:
        return ""

    lines = ["\n\n---\n\n## References\n"]
    for i, ref in enumerate(refs, 1):
        lines.append(f"{i}. [{ref['label']}]({ref['url']})")
    return "\n".join(lines)


def output_builder_node(state: ArticleGenerationState) -> dict:
    """Final assembly: package the best available article as the result."""
    logger.info("───────────────────────────────────────────────────")
    logger.info("📦 OUTPUT BUILDER NODE — Assembling final result")

    final = state.get("final_article") or state.get("article_draft") or ""

    # ── Append references section ─────────────────────────────────────────────
    references_section = _build_references_section(
        external_references=state.get("external_references") or [],
        serp_results=state.get("serp_results") or [],
    )
    if references_section:
        final = final + references_section
        logger.info("   References:     appended %d hyperlinks", references_section.count("\n1. ") + references_section.count("\n2. ") + references_section.count("\n3. ") + references_section.count("\n4. ") + references_section.count("\n5. "))

    word_count = len(final.split()) if final else 0

    logger.info("   Final article: %d words (incl. references)", word_count)
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
