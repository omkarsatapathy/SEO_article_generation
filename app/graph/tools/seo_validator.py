import json
import re
from typing import List

from langchain_core.tools import tool

from app.config import settings
from app.graph.state import Keyword, QAResult, SeoMetadata
from config.config import cfg


@tool
def seo_validator_tool(
    article: str,
    metadata_json: str,
    keywords_json: str,
    target_word_count: int,
) -> str:
    """Programmatic SEO quality checker — no LLM calls."""
    # Use model_construct to skip field validators — the tool itself performs
    # the length / content checks rather than delegating to Pydantic.
    raw_meta = json.loads(metadata_json)
    metadata = SeoMetadata.model_construct(**raw_meta)
    keywords: List[Keyword] = [
        Keyword.model_validate(k) for k in json.loads(keywords_json)
    ]

    # Load thresholds and penalties from config
    hp_t = cfg.hyperparams.qa.thresholds
    hp_p = cfg.hyperparams.qa.penalties
    tolerance = hp_t.word_count_tolerance

    # Identify primary keyword
    primary_kw = next(
        (k.word for k in keywords if k.is_primary),
        keywords[0].word if keywords else "",
    )
    secondary_kws = [k.word for k in keywords if not k.is_primary]

    score = 100
    issues: List[str] = []
    suggestions: List[str] = []

    # ── Helpers ──────────────────────────────────────────────────────────────
    all_words = article.split()
    total_words = len(all_words)

    h1_matches = re.findall(r"^#\s+(.+)$", article, re.MULTILINE)
    h2_matches = re.findall(r"^##\s+(.+)$", article, re.MULTILINE)
    h3_matches = re.findall(r"^###\s+(.+)$", article, re.MULTILINE)

    kw_count = len(re.findall(re.escape(primary_kw), article, re.IGNORECASE))
    kw_word_len = len(primary_kw.split())
    keyword_density = (kw_count * kw_word_len / total_words * 100) if total_words else 0

    # ── Check 1: PRIMARY_KEYWORD_IN_H1 ───────────────────────────────────────
    if h1_matches:
        if primary_kw.lower() not in h1_matches[0].lower():
            score -= hp_p.keyword_in_h1
            issues.append(
                f"PRIMARY_KEYWORD_IN_H1: '{primary_kw}' not found in H1 heading."
            )
        else:
            suggestions.append("H1 contains the primary keyword — good start.")
    else:
        score -= hp_p.keyword_in_h1
        issues.append("PRIMARY_KEYWORD_IN_H1: No H1 heading found in article.")

    # ── Check 2: PRIMARY_KEYWORD_IN_INTRO ────────────────────────────────────
    # Strip the H1 line, then look at first N chars of the remainder
    body_without_h1 = re.sub(r"^#\s+.+\n?", "", article, count=1, flags=re.MULTILINE)
    intro = body_without_h1[:hp_t.intro_check_length]
    if primary_kw.lower() not in intro.lower():
        score -= hp_p.keyword_in_intro
        issues.append(
            f"PRIMARY_KEYWORD_IN_INTRO: '{primary_kw}' not found in the opening "
            f"{hp_t.intro_check_length} characters."
        )
    else:
        suggestions.append("Primary keyword appears early in the article — well done.")

    # ── Check 3 & 9: KEYWORD_DENSITY / NO_KEYWORD_STUFFING ───────────────────
    if keyword_density > hp_t.keyword_density_max:
        score -= hp_p.keyword_density_out_of_range
        issues.append(
            f"KEYWORD_DENSITY: Density is {keyword_density:.2f}% — outside the "
            f"{hp_t.keyword_density_min}-{hp_t.keyword_density_max}% target range."
        )
        # Check 9: stuffing
        score -= hp_p.keyword_stuffing
        issues.append(
            f"NO_KEYWORD_STUFFING: Keyword density {keyword_density:.2f}% exceeds "
            f"{hp_t.keyword_density_max}% — keyword stuffing detected."
        )
    elif keyword_density < hp_t.keyword_density_min:
        score -= hp_p.keyword_density_out_of_range
        issues.append(
            f"KEYWORD_DENSITY: Density is {keyword_density:.2f}% — below the "
            f"{hp_t.keyword_density_min}% minimum."
        )
        suggestions.append("Add the primary keyword more naturally throughout the article.")
    else:
        suggestions.append(f"Keyword density is {keyword_density:.2f}% — within optimal range.")

    # ── Check 4: H2_KEYWORD_COVERAGE ─────────────────────────────────────────
    all_kws_lower = [primary_kw.lower()] + [s.lower() for s in secondary_kws]
    h2_with_kw = [
        h2 for h2 in h2_matches
        if any(kw in h2.lower() for kw in all_kws_lower)
    ]
    if len(h2_with_kw) < hp_t.h2_keyword_coverage_min:
        score -= hp_p.h2_keyword_coverage
        issues.append(
            f"H2_KEYWORD_COVERAGE: Only {len(h2_with_kw)} H2 heading(s) contain a keyword. "
            f"At least {hp_t.h2_keyword_coverage_min} required."
        )
    else:
        suggestions.append(f"{len(h2_with_kw)} H2 headings include target keywords — great structure.")

    # ── Check 5: WORD_COUNT_TARGET (scaled penalty) ──────────────────────────
    lower_bound = target_word_count * (1.0 - tolerance)
    upper_bound = target_word_count * (1.0 + tolerance)
    if not (lower_bound <= total_words <= upper_bound):
        if total_words < lower_bound:
            ratio = total_words / target_word_count if target_word_count else 0
            if ratio < hp_t.word_count_ratio_significant:
                penalty = hp_p.word_count_severe
            elif ratio < hp_t.word_count_ratio_marginal:
                penalty = hp_p.word_count_significant
            else:
                penalty = hp_p.word_count_marginal
        else:
            over_ratio = total_words / target_word_count if target_word_count else 1
            if over_ratio > hp_t.word_count_over_ratio_extreme:
                penalty = hp_p.word_count_severe
            elif over_ratio > hp_t.word_count_over_ratio_significant:
                penalty = hp_p.word_count_significant
            else:
                penalty = hp_p.word_count_marginal
        score -= penalty
        issues.append(
            f"WORD_COUNT_TARGET: Article has {total_words} words; target is "
            f"{target_word_count} ±{int(tolerance * 100)}% ({int(lower_bound)}-{int(upper_bound)}). "
            f"Penalty: -{penalty} points."
        )
        if total_words < target_word_count * hp_t.word_count_ratio_significant:
            issues.append(
                f"SEVERE_WORD_DEFICIT: Article is only {total_words}/{target_word_count} words "
                f"({int(ratio * 100)}% of target). Every section must be expanded substantially."
            )
    else:
        suggestions.append(f"Word count ({total_words}) is within the target range.")

    # ── Check 6: TITLE_TAG_LENGTH ─────────────────────────────────────────────
    if len(metadata.title_tag) > hp_t.title_tag_max:
        score -= hp_p.title_tag_length
        issues.append(
            f"TITLE_TAG_LENGTH: Title tag is {len(metadata.title_tag)} chars — "
            f"must be ≤{hp_t.title_tag_max}."
        )
    else:
        if len(metadata.title_tag) > hp_t.title_tag_suggestion_threshold:
            suggestions.append(
                f"Title tag length is good; keep it under {hp_t.title_tag_max} characters."
            )

    # ── Check 7: META_DESCRIPTION_LENGTH ─────────────────────────────────────
    if len(metadata.meta_description) > hp_t.meta_description_max:
        score -= hp_p.meta_description_length
        issues.append(
            f"META_DESCRIPTION_LENGTH: Meta description is {len(metadata.meta_description)} chars — "
            f"must be ≤{hp_t.meta_description_max}."
        )
    else:
        if len(metadata.meta_description) > hp_t.meta_description_suggestion_threshold:
            suggestions.append("Meta description length is fine; ideally keep it under 155 chars.")

    # ── Check 8: HEADING_HIERARCHY ────────────────────────────────────────────
    hierarchy_ok = True
    if not h1_matches:
        hierarchy_ok = False
        # issue already added in check 1; avoid double-reporting
    elif len(h1_matches) > 1:
        hierarchy_ok = False
        issues.append("HEADING_HIERARCHY: Multiple H1 headings found — only one is allowed.")

    if hierarchy_ok and h3_matches and not h2_matches:
        hierarchy_ok = False
        issues.append("HEADING_HIERARCHY: H3 headings appear without any H2 — invalid hierarchy.")

    if hierarchy_ok:
        # Check that no H3 appears before the first H2
        first_h2 = re.search(r"^##\s", article, re.MULTILINE)
        first_h3 = re.search(r"^###\s", article, re.MULTILINE)
        if first_h3 and first_h2 and first_h3.start() < first_h2.start():
            hierarchy_ok = False
            issues.append("HEADING_HIERARCHY: An H3 appears before the first H2 — invalid hierarchy.")

    if not hierarchy_ok:
        score -= hp_p.heading_hierarchy

    # ── Check 10: MIN_SECTION_LENGTH ──────────────────────────────────────────
    h2_split_pattern = re.compile(r"(?=^##\s)", re.MULTILINE)
    sections = h2_split_pattern.split(article)
    # Drop everything before the first H2
    h2_sections = [s for s in sections if re.match(r"^##\s", s)]
    short_sections = [
        re.match(r"^##\s+(.+)", s).group(1)  # type: ignore[union-attr]
        for s in h2_sections
        if len(s.split()) < hp_t.min_section_words
    ]
    if short_sections:
        score -= hp_p.short_section
        issues.append(
            f"MIN_SECTION_LENGTH: {len(short_sections)} H2 section(s) have fewer than "
            f"{hp_t.min_section_words} words: "
            + ", ".join(f"'{t}'" for t in short_sections)
        )
    else:
        suggestions.append("All H2 sections meet the minimum length requirement.")

    # ── Check 11: LINK_PLACEHOLDERS ──────────────────────────────────────────
    placeholder_count = len(re.findall(r"(?:INTERNAL|EXTERNAL)_LINK_PLACEHOLDER", article))
    if placeholder_count:
        score -= hp_p.link_placeholders
        issues.append(
            f"LINK_PLACEHOLDERS: Article contains {placeholder_count} unresolved "
            "link placeholder(s) — these must be removed or replaced."
        )

    # ── Check 12: CONTENT_COMPLETENESS ───────────────────────────────────────
    # Detect mid-word truncation (the article was cut off by token limits)
    stripped = article.rstrip()
    if stripped:
        last_line = stripped.rsplit('\n', 1)[-1].strip()
        # If the last non-empty line is body text (not a heading) and doesn't
        # end with sentence-ending punctuation, flag as truncated.
        if last_line and not last_line.startswith('#') and not last_line[-1] in '.!?")\u2019\u201d\u2014\u2026':
            score -= hp_p.content_truncated
            issues.append(
                "CONTENT_COMPLETENESS: Article appears truncated — the last sentence "
                "does not end with proper punctuation."
            )

    qa_result = QAResult(
        score=max(0, score),
        passed=(score >= settings.QA_PASS_SCORE),
        issues=issues,
        suggestions=suggestions,
    )
    return qa_result.model_dump_json()
