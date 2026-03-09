"""Surgical tests for _coerce_links — the function that kept crashing writer_node."""
import pytest

from app.graph.nodes.writer import _coerce_links
from app.graph.state import ExternalReference, InternalLink, LinkingSuggestions


# ── Case 1: LLM returns plain strings (the exact failure from logs) ───────────

def test_coerce_links_handles_plain_strings():
    """The LLM returned flat string lists — this was the original crash."""
    payload = {
        "internal_links": [
            "China GDP & Economic Indicators",
            "China Property Market & Financial Stability",
            "China Trade, Exports & Global Supply Chains",
        ],
        "external_references": [
            "https://www.worldbank.org/en/country/china/overview",
            "https://www.imf.org/en/Countries/CHN",
            "http://www.stats.gov.cn/english/",
        ],
    }
    result = _coerce_links(payload)
    assert isinstance(result, LinkingSuggestions)
    assert len(result.internal) == 3
    assert len(result.external) == 3
    # Internal strings become both anchor_text and suggested_target_topic
    assert result.internal[0].anchor_text == "China GDP & Economic Indicators"
    assert result.internal[0].suggested_target_topic == "China GDP & Economic Indicators"
    # External strings become source_url with empty context
    assert result.external[0].source_url == "https://www.worldbank.org/en/country/china/overview"
    assert result.external[0].context == ""


# ── Case 2: Properly structured dicts (happy path) ───────────────────────────

def test_coerce_links_handles_proper_dicts():
    payload = {
        "internal_links": [
            {"anchor_text": "China economy", "suggested_target_topic": "China GDP"},
        ],
        "external_references": [
            {"source_url": "https://example.com", "context": "In the intro"},
        ],
    }
    result = _coerce_links(payload)
    assert isinstance(result, LinkingSuggestions)
    assert result.internal[0].anchor_text == "China economy"
    assert result.external[0].source_url == "https://example.com"


# ── Case 3: Keys named "internal"/"external" (from linking_tool directly) ────

def test_coerce_links_handles_internal_external_keys():
    payload = {
        "internal": [
            {"anchor_text": "link1", "suggested_target_topic": "topic1"},
        ],
        "external": [
            {"source_url": "https://example.com", "context": "paragraph 2"},
        ],
    }
    result = _coerce_links(payload)
    assert len(result.internal) == 1
    assert len(result.external) == 1


# ── Case 4: Mixed — some dicts, some strings ─────────────────────────────────

def test_coerce_links_handles_mixed_items():
    payload = {
        "internal_links": [
            {"anchor_text": "proper link", "suggested_target_topic": "topic"},
            "just a string",
        ],
        "external_references": [
            {"source_url": "https://a.com", "context": "intro"},
            "https://b.com",
        ],
    }
    result = _coerce_links(payload)
    assert len(result.internal) == 2
    assert result.internal[1].anchor_text == "just a string"
    assert len(result.external) == 2
    assert result.external[1].source_url == "https://b.com"


# ── Case 5: Empty lists ──────────────────────────────────────────────────────

def test_coerce_links_handles_empty():
    result = _coerce_links({})
    assert isinstance(result, LinkingSuggestions)
    assert result.internal == []
    assert result.external == []


# ── Case 6: Already a LinkingSuggestions object ──────────────────────────────

def test_coerce_links_passthrough():
    ls = LinkingSuggestions(internal=[], external=[])
    assert _coerce_links(ls) is ls
