import operator
from typing import Annotated, Dict, List, Optional

from pydantic import BaseModel, field_validator
from typing_extensions import TypedDict


# ── Sub-models ────────────────────────────────────────────────────────────────

class SerpResult(BaseModel):
    rank: int
    url: str
    title: str
    snippet: str


class Keyword(BaseModel):
    word: str
    frequency: int
    is_primary: bool


class OutlineSection(BaseModel):
    level: str  # "H1", "H2", "H3"
    heading: str
    keywords: List[str]
    word_target: int


class InternalLink(BaseModel):
    anchor_text: str
    suggested_target_topic: str


class ExternalReference(BaseModel):
    source_url: str
    context: str  # where in the article to place this


class SeoMetadata(BaseModel):
    title_tag: str
    meta_description: str
    primary_keyword: str
    secondary_keywords: List[str]

    @field_validator("title_tag")
    @classmethod
    def title_tag_max_60(cls, v: str) -> str:
        if len(v) > 60:
            raise ValueError(f"title_tag must be ≤60 characters (got {len(v)})")
        return v

    @field_validator("meta_description")
    @classmethod
    def meta_description_max_160(cls, v: str) -> str:
        if len(v) > 160:
            raise ValueError(f"meta_description must be ≤160 characters (got {len(v)})")
        return v


class QAResult(BaseModel):
    score: int  # ge=0, le=100 enforced below
    passed: bool
    issues: List[str]
    suggestions: List[str]

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v: int) -> int:
        if not (0 <= v <= 100):
            raise ValueError(f"score must be between 0 and 100 (got {v})")
        return v


class CompetitorStructure(BaseModel):
    url: str
    headings: List[str]


# ── Tool output models ────────────────────────────────────────────────────────

class ThemeAnalysis(BaseModel):
    """Structured output from theme extraction tool."""
    themes: List[str]
    keywords: List[Keyword]
    competitor_structures: List[CompetitorStructure]
    faqs: List[str]


class ArticleDraft(BaseModel):
    """Structured output from article writer tool."""
    content: str
    word_count: int
    sections_written: int


class OutlineOutput(BaseModel):
    """Wrapper for structured outline output."""
    sections: List[OutlineSection]


class LinkingSuggestions(BaseModel):
    """Structured output from linking tool."""
    internal: List[InternalLink]
    external: List[ExternalReference]


# ── Main shared LangGraph state ───────────────────────────────────────────────

class ArticleGenerationState(TypedDict):
    # Job metadata
    job_id: str
    topic: str
    word_count: int
    language: str
    status: str  # pending | researching | outlining | writing | qa | done | failed
    created_at: str
    updated_at: str

    # Research stage
    serp_results: Optional[List[SerpResult]]
    common_themes: Optional[List[str]]
    extracted_keywords: Optional[List[Keyword]]
    competitor_structures: Optional[List[CompetitorStructure]]
    faq_questions: Optional[List[str]]

    # Outline stage
    outline: Optional[List[OutlineSection]]

    # Writing stage
    article_draft: Optional[str]
    revision_count: int

    # QA stage
    qa_result: Optional[QAResult]

    # Final output
    final_article: Optional[str]
    seo_metadata: Optional[SeoMetadata]
    internal_links: Optional[List[InternalLink]]
    external_references: Optional[List[ExternalReference]]

    # Error tracking — append-only reducer, never overwrites
    errors: Annotated[List[str], operator.add]

    # Per-node retry counter
    retry_counts: Dict[str, int]  # {"research": 0, "outline": 0, "writer": 0, "qa": 0}
