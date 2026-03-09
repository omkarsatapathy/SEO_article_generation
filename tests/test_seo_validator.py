"""Tests for the programmatic SEO validator tool."""
import json

import pytest

from app.graph.tools.seo_validator import seo_validator_tool


# ── Helpers ────────────────────────────────────────────────────────────────────

def _meta_json(title: str = "Best Python Tips for Beginners", desc: str = "Discover the best Python tips to level up your coding skills today.") -> str:
    return json.dumps({
        "title_tag": title,
        "meta_description": desc,
        "primary_keyword": "python tips",
        "secondary_keywords": ["beginner python", "coding skills"],
    })


def _keywords_json(primary: str = "python tips") -> str:
    return json.dumps([
        {"word": primary, "frequency": 10, "is_primary": True},
        {"word": "beginner python", "frequency": 5, "is_primary": False},
        {"word": "coding skills", "frequency": 3, "is_primary": False},
    ])


def _make_article(keyword: str = "python tips", word_count: int = 500, stuff: bool = False) -> str:
    """Generate a minimal but structurally valid article."""
    if stuff:
        # Repeat the keyword excessively in a short article
        kw_block = (keyword + " ") * 50
        filler = "word " * 150
        return (
            f"# {keyword} guide\n\n"
            f"{kw_block}\n\n"
            f"## Section One with beginner python\n\n{filler}\n\n"
            f"## Section Two with coding skills\n\n{filler}\n"
        )

    # Build a normally distributed article
    section_words = max(110, word_count // 4)
    filler = "word " * section_words + "end."
    return (
        f"# The Complete Guide to {keyword}\n\n"
        f"If you want to master {keyword}, you have come to the right place. {filler}\n\n"
        f"## Understanding beginner python fundamentals\n\n{filler}\n\n"
        f"## Improving coding skills with {keyword}\n\n{filler}\n\n"
        f"## Advanced {keyword} strategies\n\n{filler}\n\n"
        f"## Conclusion\n\n{filler}\n"
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_perfect_article_scores_high():
    article = _make_article(word_count=1500)
    result_json = seo_validator_tool.invoke({
        "article": article,
        "metadata_json": _meta_json(),
        "keywords_json": _keywords_json(),
        "target_word_count": 1500,
    })
    result = json.loads(result_json)
    assert result["score"] >= 80
    assert result["passed"] is True


def test_missing_keyword_in_h1_deducts_points():
    # H1 deliberately does not contain the primary keyword
    article = (
        "# Welcome to the World of Coding\n\n"
        "python tips are everywhere today. word " * 10 + "\n\n"
        "## beginner python basics\n\n" + "word " * 120 + "\n\n"
        "## coding skills tricks\n\n" + "word " * 120 + "\n"
    )
    result_json = seo_validator_tool.invoke({
        "article": article,
        "metadata_json": _meta_json(),
        "keywords_json": _keywords_json(),
        "target_word_count": len(article.split()),
    })
    result = json.loads(result_json)
    assert any("H1" in issue for issue in result["issues"])


def test_title_tag_too_long():
    long_title = "A" * 80  # 80 chars — exceeds 60-char limit
    result_json = seo_validator_tool.invoke({
        "article": _make_article(word_count=1500),
        "metadata_json": _meta_json(title=long_title),
        "keywords_json": _keywords_json(),
        "target_word_count": 1500,
    })
    result = json.loads(result_json)
    assert any("TITLE_TAG_LENGTH" in issue for issue in result["issues"])
    assert result["score"] < 100


def test_word_count_off_target():
    # Article is ~500 words but target is 1500 — well outside ±15%
    article = _make_article(word_count=500)
    result_json = seo_validator_tool.invoke({
        "article": article,
        "metadata_json": _meta_json(),
        "keywords_json": _keywords_json(),
        "target_word_count": 1500,
    })
    result = json.loads(result_json)
    assert any("WORD_COUNT_TARGET" in issue for issue in result["issues"])


def test_keyword_stuffing_detected():
    article = _make_article(keyword="python tips", word_count=1500, stuff=True)
    result_json = seo_validator_tool.invoke({
        "article": article,
        "metadata_json": _meta_json(),
        "keywords_json": _keywords_json(),
        "target_word_count": len(article.split()),
    })
    result = json.loads(result_json)
    assert any("STUFFING" in issue or "stuffing" in issue.lower() for issue in result["issues"])

