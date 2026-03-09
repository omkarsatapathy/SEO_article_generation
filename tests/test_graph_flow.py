"""Tests for graph assembly and conditional routing."""
import json
from unittest.mock import patch

from app.graph.graph_builder import build_graph, route_after_qa


def test_graph_compiles_without_checkpointer():
    graph = build_graph(checkpointer=None)
    assert graph is not None


def test_graph_has_all_nodes():
    graph = build_graph(checkpointer=None)
    node_names = set(graph.get_graph().nodes.keys())
    expected = {"orchestrator", "research", "outline", "writer", "qa", "output", "error_handler"}
    assert expected.issubset(node_names)


def test_route_after_qa_done():
    mock_state = {
        "status": "done",
        "revision_count": 0,
        "topic": "test",
        "word_count": 1500,
        "language": "en",
        "job_id": "test-id",
        "created_at": "",
        "updated_at": "",
        "retry_counts": {"research": 0, "outline": 0, "writer": 0, "qa": 0},
        "errors": [],
        "serp_results": None,
        "common_themes": None,
        "extracted_keywords": None,
        "competitor_structures": None,
        "faq_questions": None,
        "outline": None,
        "article_draft": None,
        "qa_result": None,
        "final_article": None,
        "seo_metadata": None,
        "internal_links": None,
        "external_references": None,
    }
    assert route_after_qa(mock_state) == "output"


def test_full_pipeline_with_mock_serp():
    """Integration test: full pipeline with all LLM calls mocked out."""
    from app.graph.state import (
        ArticleDraft,
        ExternalReference,
        InternalLink,
        Keyword,
        LinkingSuggestions,
        OutlineOutput,
        OutlineSection,
        SeoMetadata,
        SerpResult,
        ThemeAnalysis,
    )

    topic = "best productivity tools for remote teams"
    kw = "productivity tools"
    p = "word "
    sec_filler = p * 342  # 342 filler words per H2 section body

    # ── Mock SERP results ──────────────────────────────────────────────────────
    serp_results = [
        SerpResult(
            rank=i + 1,
            url=f"https://example{i}.com/productivity",
            title=f"Best {kw}: Guide #{i + 1}",
            snippet=f"Comprehensive guide to {kw} for distributed remote teams. Part {i + 1}.",
        )
        for i in range(10)
    ]

    # ── Mock ThemeAnalysis ─────────────────────────────────────────────────────
    theme_analysis = ThemeAnalysis(
        themes=["productivity", "remote work", "collaboration", "tools", "time management"],
        keywords=[
            Keyword(word="productivity tools", frequency=8, is_primary=True),
            Keyword(word="remote teams", frequency=6, is_primary=False),
            Keyword(word="collaboration software", frequency=4, is_primary=False),
        ],
        competitor_structures=[],
        faqs=["What are the best productivity tools for remote teams?"],
    )

    # ── Mock OutlineOutput ─────────────────────────────────────────────────────
    outline = OutlineOutput(
        sections=[
            OutlineSection(level="H1", heading=f"Best {kw} for Remote Teams", keywords=[kw], word_target=100),
            OutlineSection(level="H2", heading=f"Top {kw} for Collaboration", keywords=[kw, "remote teams"], word_target=350),
            OutlineSection(level="H2", heading=f"Managing Projects with {kw}", keywords=[kw], word_target=350),
            OutlineSection(level="H2", heading=f"How {kw} Boost Team Output", keywords=[kw], word_target=350),
            OutlineSection(level="H2", heading=f"Choosing the Best {kw} for Your Team", keywords=[kw], word_target=350),
            OutlineSection(level="H2", heading=f"Conclusion on {kw}", keywords=[kw], word_target=100),
        ]
    )

    # ── Mock ArticleDraft (~1 600 words, passes all 10 SEO checks) ─────────────
    # keyword density ~1.75 %, word count within ±15 % of 1500, all sections >100 words
    article_content = (
        f"# Best {kw} for Remote Teams\n\n"
        f"Remote teams need {kw} to stay efficient. "
        f"Choosing the right {kw} makes all the difference. "
        f"This guide covers the top {kw} available today. "
        + p * 86 + "\n\n"
        f"## Top {kw} for Collaboration\n\n"
        f"Using {kw} effectively transforms remote teamwork. "
        + sec_filler + "\n\n"
        f"## Managing Projects with {kw}\n\n"
        f"Project {kw} streamline daily workflows. "
        + sec_filler + "\n\n"
        f"## How {kw} Boost Team Output\n\n"
        f"The best {kw} increase team output measurably. "
        + sec_filler + "\n\n"
        f"## Choosing the Best {kw} for Your Team\n\n"
        f"Selecting {kw} depends on team size and needs. "
        + sec_filler + "\n\n"
        f"## Conclusion on {kw}\n\n"
        f"Investing in {kw} pays dividends for distributed teams. "
        + p * 44 + "\n"
    )
    article_draft = ArticleDraft(
        content=article_content,
        word_count=len(article_content.split()),
        sections_written=5,
    )

    # ── Mock SeoMetadata (must satisfy Pydantic validators) ───────────────────
    metadata = SeoMetadata(
        title_tag="Best Productivity Tools for Remote Teams",      # 41 chars ≤ 60 ✓
        meta_description=(
            "Discover the best productivity tools for remote teams. "
            "Boost collaboration and output today."
        ),                                                          # 92 chars ≤ 160 ✓
        primary_keyword="productivity tools",
        secondary_keywords=["remote teams", "collaboration software"],
    )

    # ── Mock LinkingSuggestions ────────────────────────────────────────────────
    links = LinkingSuggestions(
        internal=[
            InternalLink(anchor_text="project management guide", suggested_target_topic="project management"),
            InternalLink(anchor_text="remote work tips", suggested_target_topic="remote work best practices"),
            InternalLink(anchor_text="team collaboration tools", suggested_target_topic="team collaboration"),
        ],
        external=[
            ExternalReference(
                source_url="https://hbr.org/topic/remote-work",
                context="In the intro when citing remote work adoption statistics",
            ),
            ExternalReference(
                source_url="https://www.forbes.com/advisor/business/software/best-project-management-software/",
                context="In the project management section for third-party validation",
            ),
        ],
    )

    # ── Patch all LLM-backed tools at their usage sites ───────────────────────
    with (
        patch("app.graph.nodes.research.serp_fetch_tool") as mock_serp,
        patch("app.graph.nodes.research.theme_extractor_tool") as mock_theme,
        patch("app.graph.nodes.outline.outline_builder_tool") as mock_outline,
        patch("app.graph.nodes.writer.article_writer_tool") as mock_writer,
        patch("app.graph.nodes.writer.metadata_generator_tool") as mock_meta,
        patch("app.graph.nodes.writer.linking_tool") as mock_linking,
    ):
        mock_serp.invoke.return_value = json.dumps([r.model_dump() for r in serp_results])
        mock_theme.invoke.return_value = theme_analysis.model_dump_json()
        mock_outline.invoke.return_value = outline.model_dump_json()
        mock_writer.invoke.return_value = article_draft.model_dump_json()
        mock_meta.invoke.return_value = metadata.model_dump_json()
        mock_linking.invoke.return_value = links.model_dump_json()

        graph = build_graph(checkpointer=None)
        initial_state = {
            "topic": topic,
            "word_count": 1500,
            "language": "en",
            "status": "pending",
            "job_id": "",
            "created_at": "",
            "updated_at": "",
            "retry_counts": {"research": 0, "outline": 0, "writer": 0, "qa": 0},
            "revision_count": 0,
            "errors": [],
            "serp_results": None,
            "common_themes": None,
            "extracted_keywords": None,
            "competitor_structures": None,
            "faq_questions": None,
            "outline": None,
            "article_draft": None,
            "qa_result": None,
            "final_article": None,
            "seo_metadata": None,
            "internal_links": None,
            "external_references": None,
        }

        final_state = graph.invoke(initial_state)

    # ── Assertions ─────────────────────────────────────────────────────────────
    assert final_state["status"] == "done"
    assert final_state.get("final_article") is not None
    assert final_state.get("seo_metadata") is not None
    assert len(final_state.get("internal_links") or []) >= 3
    assert len(final_state.get("external_references") or []) >= 2
    assert final_state["qa_result"].score >= 0

