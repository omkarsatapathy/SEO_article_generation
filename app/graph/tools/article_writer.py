import json
import logging
import re
from typing import Any, Dict, List, Tuple

from langchain_core.tools import tool

from app.graph.state import ArticleDraft
from config.config import cfg

logger = logging.getLogger(__name__)


def _group_h2_blocks(
    sections: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any] | None, List[Dict[str, Any]]]:
    """Group outline sections into (H1, list of H2 blocks).

    Each H2 block is ``{"h2": <section>, "h3s": [<section>, ...]}``.
    """
    h1 = None
    blocks: List[Dict[str, Any]] = []
    current_block: Dict[str, Any] | None = None

    for s in sections:
        level = s.get("level", "")
        if level == "H1":
            h1 = s
        elif level == "H2":
            if current_block:
                blocks.append(current_block)
            current_block = {"h2": s, "h3s": []}
        elif level == "H3" and current_block is not None:
            current_block["h3s"].append(s)

    if current_block:
        blocks.append(current_block)

    return h1, blocks


def _llm_text(llm, prompt: str) -> str:
    """Invoke the LLM and return the text content."""
    response = llm.invoke(prompt)
    return (response.content if hasattr(response, "content") else str(response)).strip()


def _word_count(text: str) -> int:
    return len(text.split())


def _generate_intro(
    llm,
    h1_heading: str,
    primary_kw: str,
    themes_json: str,
    language: str,
    qa_feedback: str,
    research_context: str = "",
) -> str:
    """Generate the intro paragraph."""
    hp = cfg.hyperparams.writing
    qa_block = f"\n⚠️ QA REVISION FEEDBACK — address these issues:\n{qa_feedback}\n" if qa_feedback else ""
    research_block = f"\nResearch context (use for factual grounding):\n{research_context}\n" if research_context else ""
    prompt = cfg.prompts.tools.intro.format(
        h1_heading=h1_heading,
        language=language,
        primary_kw=primary_kw,
        themes_json=themes_json,
        intro_word_min=hp.intro_word_min,
        intro_word_max=hp.intro_word_max,
        research_block=research_block,
        qa_block=qa_block,
    )
    return _llm_text(llm, prompt)


def _generate_section(
    llm,
    block: Dict[str, Any],
    primary_kw: str,
    keywords_json: str,
    themes_json: str,
    language: str,
    article_so_far: str,
    qa_feedback: str,
    remaining_budget: int | None = None,
    research_context: str = "",
) -> str:
    """Generate one H2 section (with child H3s) via raw LLM call, retry if short."""
    hp = cfg.hyperparams.writing
    h2 = block["h2"]
    h3s = block["h3s"]

    h2_heading = h2["heading"]
    h2_word_target = h2.get("word_target", 250)
    h2_keywords = h2.get("keywords", [])

    h3_instructions = ""
    total_target = h2_word_target
    for h3 in h3s:
        h3_target = h3.get("word_target", 100)
        total_target += h3_target
        h3_instructions += (
            f"\n- ### {h3['heading']} ({h3_target} words) — keywords: {h3.get('keywords', [])}"
        )

    min_words = int(total_target * hp.section_min_multiplier)
    max_words = int(total_target * hp.section_max_multiplier)
    qa_block = f"\n⚠️ QA FEEDBACK for this revision — address ALL issues:\n{qa_feedback}\n" if qa_feedback else ""

    # Budget awareness: if a remaining_budget is provided, cap so we don't overshoot
    if remaining_budget is not None and remaining_budget < total_target:
        total_target = max(remaining_budget, 100)
        min_words = int(total_target * hp.section_min_multiplier)
        max_words = int(total_target * (1.0 + (hp.section_max_multiplier - 1.0) * 0.75))

    research_block = (
        f"\nResearch context (use as factual grounding — cite insights naturally):\n{research_context}\n"
        if research_context else ""
    )

    h3_block = h3_instructions if h3_instructions else " (none — write this as a single H2 section)"
    prev_content = article_so_far[-hp.context_lookback_chars:] if article_so_far else "(First section.)"

    prompt = cfg.prompts.tools.section.format(
        language=language,
        research_block=research_block,
        qa_block=qa_block,
        h2_heading=h2_heading,
        total_target=total_target,
        min_words=min_words,
        max_words=max_words,
        h2_keywords=h2_keywords,
        h3_block=h3_block,
        primary_kw=primary_kw,
        keywords_json=keywords_json,
        themes_json=themes_json,
        h3_min_words=hp.h3_min_words,
        prev_content=prev_content,
    )

    content = _llm_text(llm, prompt)

    # ── Per-section word-count gate: retry once if too short ──────────────
    if _word_count(content) < min_words:
        logger.warning(
            "   ⚠️  Section '%s' too short: %d/%d words. Expanding…",
            h2_heading, _word_count(content), total_target,
        )
        expand_prompt = cfg.prompts.tools.section_expand.format(
            curr_word_count=_word_count(content),
            target=total_target,
            content=content,
        )
        expanded = _llm_text(llm, expand_prompt)
        if _word_count(expanded) > _word_count(content):
            content = expanded

    return content


def _generate_faq(llm, faq_questions: List[str], primary_kw: str, language: str) -> str:
    """Generate the FAQ section with all questions answered."""
    hp = cfg.hyperparams.writing
    q_list = "\n".join(f"- {q}" for q in faq_questions)
    prompt = cfg.prompts.tools.faq.format(
        language=language,
        q_list=q_list,
        primary_kw=primary_kw,
        faq_min_words=hp.faq_answer_min_words,
    )
    return _llm_text(llm, prompt)


def _generate_conclusion(llm, h1_heading: str, primary_kw: str, language: str) -> str:
    """Generate the conclusion."""
    hp = cfg.hyperparams.writing
    prompt = cfg.prompts.tools.conclusion.format(
        h1_heading=h1_heading,
        language=language,
        primary_kw=primary_kw,
        conclusion_word_min=hp.conclusion_word_min,
        conclusion_word_max=hp.conclusion_word_max,
    )
    return _llm_text(llm, prompt)


@tool
def article_writer_tool(
    outline_json: str,
    keywords_json: str,
    themes_json: str,
    language: str,
    faq_questions_json: str,
    target_word_count: int = 0,  # 0 → resolved to cfg default at runtime
    qa_feedback: str = "",
    serp_results_json: str = "[]",
    competitor_structures_json: str = "[]",
) -> str:
    """Write a complete SEO-optimised article section-by-section following the outline."""
    from app.graph.tools import get_writer_llm

    llm = get_writer_llm()
    outline = json.loads(outline_json)
    keywords = json.loads(keywords_json)
    faq_questions = json.loads(faq_questions_json)

    # Resolve default word count from config if not explicitly provided
    if not target_word_count:
        target_word_count = cfg.hyperparams.article.word_count_default

    primary_kw = next((k["word"] for k in keywords if k.get("is_primary")), "")

    h1, h2_blocks = _group_h2_blocks(outline)
    h1_heading = h1["heading"] if h1 else "Article"
    hp_w = cfg.hyperparams.writing
    max_total = int(target_word_count * hp_w.word_count_ceiling_multiplier)

    # Build a compact research context string from SERP snippets + competitor headings
    serp_results = json.loads(serp_results_json)
    competitor_structures = json.loads(competitor_structures_json)
    research_snippets = "\n".join(
        f"- [{r.get('title', '')}]: {r.get('snippet', '')}"
        for r in serp_results[:hp_w.serp_results_limit]
        if r.get("snippet")
    )
    competitor_headings = "\n".join(
        ", ".join(c.get("headings", [])[:hp_w.competitor_headings_limit])
        for c in competitor_structures[:hp_w.competitor_structures_limit]
        if c.get("headings")
    )
    research_context = ""
    if research_snippets:
        research_context += f"Research snippets (use as factual grounding):\n{research_snippets}\n"
    if competitor_headings:
        research_context += f"Competitor topic coverage examples:\n{competitor_headings}\n"

    # Detect if outline already contains FAQ / Conclusion H2s
    h2_headings_lower = [b["h2"]["heading"].lower() for b in h2_blocks]
    has_faq_section = any("faq" in h or "frequently asked" in h for h in h2_headings_lower)
    has_conclusion_section = any("conclusion" in h or "summary" in h or "final thoughts" in h for h in h2_headings_lower)

    # ── 1. H1 + Intro ────────────────────────────────────────────────────
    parts: List[str] = [f"# {h1_heading}"]
    intro = _generate_intro(llm, h1_heading, primary_kw, themes_json, language, qa_feedback, research_context)
    parts.append(intro)
    cumulative = _word_count(intro)
    logger.info("   📝 Intro: %d words (cumulative: %d/%d)", _word_count(intro), cumulative, target_word_count)

    # ── 2. Each H2 section ───────────────────────────────────────────────
    for block in h2_blocks:
        remaining = max_total - cumulative
        if remaining <= 50:
            logger.warning("   ⚠️  Word budget exhausted (%d/%d). Skipping remaining sections.", cumulative, max_total)
            break
        article_so_far = "\n\n".join(parts)
        section = _generate_section(
            llm, block, primary_kw, keywords_json, themes_json,
            language, article_so_far, qa_feedback,
            remaining_budget=remaining,
            research_context=research_context,
        )
        parts.append(section)
        section_wc = _word_count(section)
        cumulative += section_wc
        logger.info(
            "   📝 Section '%s': %d words (cumulative: %d/%d)",
            block["h2"]["heading"], section_wc, cumulative, target_word_count,
        )

    # ── 3. FAQ (only if not already an outline H2) ───────────────────────
    if faq_questions and not has_faq_section:
        remaining = max_total - cumulative
        if remaining > hp_w.faq_remaining_budget_min:
            faq = _generate_faq(llm, faq_questions, primary_kw, language)
            parts.append(faq)
            cumulative += _word_count(faq)
            logger.info("   📝 FAQ: %d words (cumulative: %d/%d)", _word_count(faq), cumulative, target_word_count)

    # ── 4. Conclusion (only if not already an outline H2) ────────────────
    if not has_conclusion_section:
        remaining = max_total - cumulative
        if remaining > hp_w.conclusion_remaining_budget_min:
            conclusion = _generate_conclusion(llm, h1_heading, primary_kw, language)
            parts.append(conclusion)
            cumulative += _word_count(conclusion)
            logger.info("   📝 Conclusion: %d words (cumulative: %d/%d)", _word_count(conclusion), cumulative, target_word_count)

    # ── 5. Assemble & report ─────────────────────────────────────────────
    full_article = "\n\n".join(parts)
    total_words = _word_count(full_article)
    sections_written = len(h2_blocks)

    logger.info(
        "   ✅ Article assembled: %d words across %d H2 sections (target: %d)",
        total_words, sections_written, target_word_count,
    )

    draft = ArticleDraft(
        content=full_article,
        word_count=total_words,
        sections_written=sections_written,
    )
    return draft.model_dump_json()

