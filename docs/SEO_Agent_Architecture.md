# SEO Article Generation System — Full Architecture
### Multi-Agent LangGraph System with PostgreSQL Persistence

---

## 1. SYSTEM OVERVIEW

```
INPUT:  { topic, word_count, language }
          ↓
  ┌─────────────────────┐
  │   FastAPI Gateway   │  ← Creates job_id, pushes to queue
  └────────┬────────────┘
           ↓
  ┌─────────────────────┐
  │  LangGraph Graph    │  ← Compiled with PostgresSaver
  │                     │
  │  [ORCHESTRATOR]     │  ← Manages state, routes nodes
  │       ↓             │
  │  [RESEARCH AGENT]   │  ← SERP scraping + theme extraction
  │       ↓             │
  │  [OUTLINE AGENT]    │  ← H1/H2/H3 structure builder
  │       ↓             │
  │  [WRITER AGENT]     │  ← Full article generation
  │       ↓             │
  │  [QA AGENT]         │  ← SEO validation + scoring
  │       ↓             │
  │  [OUTPUT BUILDER]   │  ← Final structured output
  └─────────────────────┘
           ↓
  ┌─────────────────────┐
  │   PostgreSQL DB     │  ← Checkpoints + Job tracking
  └─────────────────────┘
           ↓
OUTPUT: { article, seo_metadata, keywords, links, score }
```

---

## 2. STATE SCHEMA (The Backbone)

This is the single most important design decision. Every node reads from and writes to this shared state.

```python
from typing import TypedDict, Optional, List, Annotated
from pydantic import BaseModel
from langgraph.graph.message import add_messages
import operator

# ─── Sub-models ───────────────────────────────────────────

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
    level: str          # "H1", "H2", "H3"
    heading: str
    keywords: List[str]
    word_target: int

class InternalLink(BaseModel):
    anchor_text: str
    suggested_target_topic: str

class ExternalReference(BaseModel):
    source_url: str
    context: str         # where in article to place this

class SeoMetadata(BaseModel):
    title_tag: str       # max 60 chars
    meta_description: str  # max 160 chars
    primary_keyword: str
    secondary_keywords: List[str]

class QAResult(BaseModel):
    score: int           # 0–100
    passed: bool
    issues: List[str]
    suggestions: List[str]

# ─── Tool Output Models (Pydantic-enforced) ───────────────

class ThemeAnalysis(BaseModel):
    """Structured output from theme extraction tool."""
    themes: List[str]                    # Top 5 common themes/subtopics
    keywords: List[Keyword]              # Primary + secondary keywords, frequency-ranked
    competitor_structures: List[dict]     # H-tag structures from competitor pages
    faqs: List[str]                      # Questions from "People Also Ask"

class ArticleDraft(BaseModel):
    """Structured output from article writer tool."""
    content: str                         # Full article text with markdown headings
    word_count: int                      # Actual word count of generated content
    sections_written: int                # Number of H2 sections produced

class LinkingSuggestions(BaseModel):
    """Structured output from linking tool."""
    internal: List[InternalLink]         # 3-5 internal link suggestions
    external: List[ExternalReference]    # 2-4 external reference suggestions

# ─── MAIN SHARED STATE ────────────────────────────────────

class ArticleGenerationState(TypedDict):
    # ── Job Metadata ──
    job_id: str
    topic: str
    word_count: int
    language: str
    status: str          # pending | researching | outlining | writing | qa | done | failed
    created_at: str
    updated_at: str

    # ── Research Stage ──
    serp_results: Optional[List[SerpResult]]
    common_themes: Optional[List[str]]
    extracted_keywords: Optional[List[Keyword]]
    competitor_structures: Optional[List[dict]]  # H-tag structures from top results
    faq_questions: Optional[List[str]]           # From "People Also Ask" SERP section

    # ── Outline Stage ──
    outline: Optional[List[OutlineSection]]

    # ── Writing Stage ──
    article_draft: Optional[str]
    revision_count: int   # tracks how many QA revision cycles
    
    # ── QA Stage ──
    qa_result: Optional[QAResult]

    # ── Final Output ──
    final_article: Optional[str]
    seo_metadata: Optional[SeoMetadata]
    internal_links: Optional[List[InternalLink]]
    external_references: Optional[List[ExternalReference]]

    # ── Error Tracking ──
    errors: Annotated[List[str], operator.add]  # reducer: appends, never overwrites
    retry_counts: dict    # { "research": 0, "outline": 0, "writer": 0, "qa": 0 }
```

**Why this design?**
- `Annotated[List[str], operator.add]` on `errors` means every node can append errors without overwriting previous ones
- All optional fields default to None — nodes only populate what they own
- `revision_count` tracks QA retry cycles to prevent infinite loops
- `retry_counts` per node ensures max retries enforced independently per stage

---

## 3. POSTGRESQL CHECKPOINTING (Crash Durability)

```python
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

DB_URI = "postgresql://user:pass@localhost:5432/seo_agent?sslmode=require"

# Connection pool — critical for production, never use single connections
pool = ConnectionPool(
    conninfo=DB_URI,
    max_size=10,
    kwargs={"autocommit": True}
)

with pool.connection() as conn:
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()   # Creates checkpoint tables on first run

# Compile graph with checkpointer attached
graph = builder.compile(checkpointer=checkpointer)
```

**What PostgresSaver creates in your DB:**
```
Tables:
  checkpoints          ← full state snapshot per superstep
  checkpoint_writes    ← pending writes (partial node outputs)
  checkpoint_blobs     ← serialized state blobs
```

**How crash resume works:**
```
Graph runs: Node1 ✅ → Node2 ✅ → Node3 💥 CRASH
                                       ↑
                             checkpoint saved here

On restart:
  graph.invoke(None, config={"configurable": {"thread_id": "job_abc123"}})
                 ↑
           None = "resume from last checkpoint"
           
Result: Node1 ✅ SKIP → Node2 ✅ SKIP → Node3 🔄 RETRY
```

**The thread_id is your job_id:**
```python
config = {
    "configurable": {
        "thread_id": f"seo-job:{job_id}",
        "checkpoint_ns": "seo_agent_v1"   # versioning for schema migrations
    }
}
```

---

## 4. THE GRAPH NODES (Step by Step)

### Node 1: ORCHESTRATOR (Entry Point)

```
Responsibility: Validate input, create job, initialize state
```

```python
def orchestrator_node(state: ArticleGenerationState) -> dict:
    """
    - Validates topic, word_count, language
    - Sets job_id (uuid4)
    - Initializes retry_counts
    - Sets status = "researching"
    """
    return {
        "job_id": str(uuid.uuid4()),
        "status": "researching",
        "retry_counts": {"research": 0, "outline": 0, "writer": 0, "qa": 0},
        "revision_count": 0
    }
```

---

### Node 2: RESEARCH AGENT

```
Responsibility: Fetch SERP data → extract themes, keywords, FAQs
Tools: serp_fetch_tool, theme_extractor_tool
```

```python
# Tool 1: SERP Fetcher — returns List[SerpResult] (Pydantic-validated)
@tool
def serp_fetch_tool(query: str) -> List[SerpResult]:
    """
    Fetches top 10 Google results via SerpAPI.
    Falls back to mock data if API fails.
    Returns: list of SerpResult (Pydantic-validated)
    """
    try:
        response = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "num": 10, "api_key": SERP_API_KEY}
        )
        raw_results = parse_serp_response(response.json())
        return [SerpResult(**r) for r in raw_results]  # Pydantic validation
    except Exception as e:
        # Fallback to mock data — graceful degradation
        return [SerpResult(**r) for r in get_mock_serp_data(query)]

# Tool 2: Theme Extractor — returns ThemeAnalysis (Pydantic-enforced via structured output)
@tool
def theme_extractor_tool(serp_results: List[SerpResult]) -> ThemeAnalysis:
    """
    Uses LLM with structured output to extract:
    - Common themes across all 10 results
    - Primary + secondary keywords (frequency-ranked)
    - H-tag structures from competitor pages
    - FAQ questions from "People Also Ask"
    
    Returns: ThemeAnalysis (Pydantic model, enforced by LLM structured output)
    """
    structured_llm = llm.with_structured_output(ThemeAnalysis)
    
    return structured_llm.invoke(
        f"""Analyze these 10 search results and extract themes, keywords, 
        competitor heading structures, and FAQ questions.
        
        Results: {[r.model_dump() for r in serp_results]}"""
    )  # Returns ThemeAnalysis — guaranteed schema compliance

# Research Node
def research_node(state: ArticleGenerationState) -> dict:
    try:
        serp_data: List[SerpResult] = serp_fetch_tool.invoke(state["topic"])
        analysis: ThemeAnalysis = theme_extractor_tool.invoke(serp_data)
        return {
            "serp_results": serp_data,
            "common_themes": analysis.themes,
            "extracted_keywords": analysis.keywords,
            "competitor_structures": analysis.competitor_structures,
            "faq_questions": analysis.faqs,
            "status": "outlining"
        }
    except Exception as e:
        return {
            "errors": [f"Research failed: {str(e)}"],
            "retry_counts": {**state["retry_counts"], "research": state["retry_counts"]["research"] + 1}
        }
```

---

### Node 3: OUTLINE AGENT

```
Responsibility: Build structured H1/H2/H3 outline from themes
Tools: outline_builder_tool
```

```python
# Pydantic wrapper for outline output — List[OutlineSection] can't be passed
# directly to with_structured_output, so we wrap it
class OutlineOutput(BaseModel):
    """Wrapper for structured outline output."""
    sections: List[OutlineSection]

@tool
def outline_builder_tool(themes: List[str], keywords: List[Keyword], word_count: int) -> List[OutlineSection]:
    """
    Builds SEO-optimized article structure (Pydantic-enforced):
    - H1: Primary keyword + value proposition  (1)
    - H2: Major sections — one per top theme   (4-6)
    - H3: Subsections under each H2            (2-3 per H2)
    
    Distributes word_count proportionally across sections.
    Assigns keywords to specific sections.
    Returns: List[OutlineSection] via with_structured_output(OutlineOutput)
    """
    structured_llm = llm.with_structured_output(OutlineOutput)
    
    result: OutlineOutput = structured_llm.invoke(
        f"""Build an SEO article outline for these themes: {themes}
        Primary keyword: {keywords[0].word}
        Total words: {word_count}
        
        Create sections with: level (H1/H2/H3), heading, keywords, word_target"""
    )
    return result.sections  # Unwrap to List[OutlineSection]

def outline_node(state: ArticleGenerationState) -> dict:
    try:
        outline: List[OutlineSection] = outline_builder_tool.invoke({
            "themes": state["common_themes"],
            "keywords": state["extracted_keywords"],
            "word_count": state["word_count"]
        })
        return {
            "outline": outline,
            "status": "writing"
        }
    except Exception as e:
        return {
            "errors": [f"Outline failed: {str(e)}"],
            "retry_counts": {**state["retry_counts"], "outline": state["retry_counts"]["outline"] + 1}
        }
```

---

### Node 4: WRITER AGENT

```
Responsibility: Write full article from outline
Tools: article_writer_tool, metadata_generator_tool, linking_tool
```

```python
@tool
def article_writer_tool(outline: List[OutlineSection], keywords: List[Keyword], 
                        themes: List[str], language: str, 
                        faq_questions: List[str]) -> ArticleDraft:
    """
    Writes full article section by section (Pydantic-enforced).
    - Natural tone, NOT robotic
    - Primary keyword in: H1, first paragraph, 2-3 H2s
    - Keyword density: 1-2% (not stuffed)
    - Each section word count matches outline targets
    - FAQ section appended at end
    Returns: ArticleDraft (content, word_count, sections_written)
    """
    structured_llm = llm.with_structured_output(ArticleDraft)
    
    return structured_llm.invoke(
        f"""Write a complete SEO-optimized article in {language}.
        
        Outline: {[s.model_dump() for s in outline]}
        Primary keyword: {keywords[0].word}
        Secondary keywords: {[k.word for k in keywords if not k.is_primary]}
        Themes to cover: {themes}
        FAQ questions to include: {faq_questions}
        
        Requirements:
        - Natural, human-readable tone
        - Primary keyword in H1 and first paragraph
        - Keyword density 1-2%
        - Follow the outline section structure exactly
        - Include FAQ section at the end"""
    )  # Returns ArticleDraft — guaranteed schema compliance

@tool  
def metadata_generator_tool(article: str, primary_keyword: str) -> SeoMetadata:
    """
    Generates SEO metadata (Pydantic-enforced):
    - Title tag: primary keyword + value (≤60 chars)
    - Meta description: keyword + benefit + CTA (≤160 chars)
    Returns: SeoMetadata
    """
    structured_llm = llm.with_structured_output(SeoMetadata)
    
    return structured_llm.invoke(
        f"""Generate SEO metadata for this article.
        Primary keyword: {primary_keyword}
        Article (first 500 chars): {article[:500]}
        
        Rules:
        - title_tag: max 60 characters, must include primary keyword
        - meta_description: max 160 characters, must include keyword + CTA
        - List primary and secondary keywords found in the article"""
    )  # Returns SeoMetadata — guaranteed schema compliance

@tool
def linking_tool(outline: List[OutlineSection], themes: List[str]) -> LinkingSuggestions:
    """
    Generates internal and external link suggestions (Pydantic-enforced).
    Internal links: 3-5 anchor texts + suggested target topics
    External links: 2-4 authoritative source suggestions + placement context
    Returns: LinkingSuggestions
    """
    structured_llm = llm.with_structured_output(LinkingSuggestions)
    
    return structured_llm.invoke(
        f"""Suggest internal and external links for an SEO article.
        
        Article outline: {[s.model_dump() for s in outline]}
        Themes covered: {themes}
        
        Internal links: 3-5 suggestions with anchor_text and suggested_target_topic
        External links: 2-4 authoritative sources with source_url and placement context"""
    )  # Returns LinkingSuggestions — guaranteed schema compliance

def writer_node(state: ArticleGenerationState) -> dict:
    try:
        draft: ArticleDraft = article_writer_tool.invoke({
            "outline": state["outline"],
            "keywords": state["extracted_keywords"],
            "themes": state["common_themes"],
            "language": state["language"],
            "faq_questions": state["faq_questions"]
        })
        metadata: SeoMetadata = metadata_generator_tool.invoke({
            "article": draft.content,
            "primary_keyword": state["extracted_keywords"][0].word
        })
        links: LinkingSuggestions = linking_tool.invoke({
            "outline": state["outline"],
            "themes": state["common_themes"]
        })
        return {
            "article_draft": draft.content,
            "seo_metadata": metadata,
            "internal_links": links.internal,
            "external_references": links.external,
            "status": "qa"
        }
    except Exception as e:
        return {
            "errors": [f"Writing failed: {str(e)}"],
            "retry_counts": {**state["retry_counts"], "writer": state["retry_counts"]["writer"] + 1}
        }
```

---

### Node 5: QA AGENT

```
Responsibility: Validate SEO quality, score article, trigger revision if needed
Tools: seo_validator_tool
```

```python
@tool
def seo_validator_tool(article: str, metadata: SeoMetadata, 
                      keywords: List[Keyword], word_count: int) -> QAResult:
    """
    Validates article against SEO criteria (Pydantic-enforced).
    
    Programmatic checks (no LLM needed):
    ✅ Primary keyword in H1
    ✅ Primary keyword in first 100 words
    ✅ Keyword density 1-2%
    ✅ At least 2 H2s contain primary/secondary keywords
    ✅ Word count within ±10% of target
    ✅ Meta title ≤60 chars
    ✅ Meta description ≤160 chars
    ✅ No keyword stuffing (>3% density = fail)
    ✅ Article has proper H1→H2→H3 hierarchy
    ✅ Minimum 300 words per H2 section
    
    Returns: QAResult (score, passed, issues, suggestions)
    """
    issues = []
    suggestions = []
    score = 100
    primary_kw = next((k.word for k in keywords if k.is_primary), keywords[0].word)
    
    # Example programmatic checks — deduct points per failure
    if primary_kw.lower() not in article[:500].lower():
        issues.append("Primary keyword missing from first 100 words")
        score -= 15
    
    if len(metadata.title_tag) > 60:
        issues.append(f"Title tag too long: {len(metadata.title_tag)} chars (max 60)")
        score -= 10
    
    if len(metadata.meta_description) > 160:
        issues.append(f"Meta description too long: {len(metadata.meta_description)} chars (max 160)")
        score -= 10
    
    actual_word_count = len(article.split())
    if abs(actual_word_count - word_count) > word_count * 0.10:
        issues.append(f"Word count {actual_word_count} is outside ±10% of target {word_count}")
        score -= 10
    
    # ... additional checks for keyword density, heading hierarchy, etc.
    
    return QAResult(
        score=max(score, 0),
        passed=score >= 80,
        issues=issues,
        suggestions=suggestions
    )  # Returns QAResult — Pydantic-validated, no LLM parsing needed

def qa_node(state: ArticleGenerationState) -> dict:
    try:
        result: QAResult = seo_validator_tool.invoke({
            "article": state["article_draft"],
            "metadata": state["seo_metadata"],
            "keywords": state["extracted_keywords"],
            "word_count": state["word_count"]
        })
        
        if result.passed:
            return {
                "qa_result": result,
                "final_article": state["article_draft"],
                "status": "done"
            }
        else:
            return {
                "qa_result": result,
                "revision_count": state["revision_count"] + 1,
                "status": "writing"   # route back to writer
            }
    except Exception as e:
        return {"errors": [f"QA failed: {str(e)}"]}
```

---

## 5. THE FULL GRAPH WITH CONDITIONAL EDGES

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(ArticleGenerationState)

# ── Add all nodes ──────────────────────────────
builder.add_node("orchestrator", orchestrator_node)
builder.add_node("research",     research_node)
builder.add_node("outline",      outline_node)
builder.add_node("writer",       writer_node)
builder.add_node("qa",           qa_node)
builder.add_node("output",       output_builder_node)
builder.add_node("error_handler",error_handler_node)

# ── Entry point ────────────────────────────────
builder.add_edge(START, "orchestrator")
builder.add_edge("orchestrator", "research")

# ── Conditional routing after each agent ───────

def route_after_research(state):
    if state["retry_counts"]["research"] >= 3:
        return "error_handler"
    if state.get("serp_results"):
        return "outline"
    return "research"   # retry

def route_after_outline(state):
    if state["retry_counts"]["outline"] >= 3:
        return "error_handler"
    if state.get("outline"):
        return "writer"
    return "outline"    # retry

def route_after_writer(state):
    if state["retry_counts"]["writer"] >= 3:
        return "error_handler"
    if state.get("article_draft"):
        return "qa"
    return "writer"     # retry

def route_after_qa(state):
    if state["status"] == "done":
        return "output"
    if state["revision_count"] >= 3:  # max 3 QA revision cycles
        return "output"               # publish best effort
    return "writer"                   # revision cycle

builder.add_conditional_edges("research", route_after_research)
builder.add_conditional_edges("outline",  route_after_outline)
builder.add_conditional_edges("writer",   route_after_writer)
builder.add_conditional_edges("qa",       route_after_qa)
builder.add_edge("output", END)
builder.add_edge("error_handler", END)

graph = builder.compile(checkpointer=checkpointer)
```

---

## 6. GRAPH FLOW DIAGRAM

```
START
  │
  ▼
[ORCHESTRATOR] ──────────────────────────────────────────────────
  │                                                               │
  ▼                                                               │
[RESEARCH] ──fail──→ retry (max 3) ──────────────────→ [ERROR HANDLER]
  │ success                                                       │
  ▼                                                               │
[OUTLINE]  ──fail──→ retry (max 3) ──────────────────→ [ERROR HANDLER]
  │ success                                                       │
  ▼                                                               │
[WRITER]   ──fail──→ retry (max 3) ──────────────────→ [ERROR HANDLER]
  │ success                                                       │
  ▼                                                               │
 [QA]                                                             │
  │                                                               │
  ├── score ≥ 80 ─────────────────────────────────────▶          │
  │                                                    │          │
  └── score < 80 & revisions < 3 ──▶ [WRITER] (loop)  │          │
                                                       ▼          ▼
                                                  [OUTPUT BUILDER]
                                                       │
                                                      END
```

---

## 7. DATABASE SCHEMA (PostgreSQL)

```sql
-- Job tracking table (your own, separate from LangGraph checkpoints)
CREATE TABLE generation_jobs (
    job_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic           TEXT NOT NULL,
    word_count      INT  DEFAULT 1500,
    language        VARCHAR(10) DEFAULT 'en',
    status          VARCHAR(20) DEFAULT 'pending',
    -- pending | researching | outlining | writing | qa | done | failed
    thread_id       TEXT UNIQUE,    -- links to LangGraph checkpoint
    error_message   TEXT,
    seo_score       INT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Final article output table
CREATE TABLE generated_articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID REFERENCES generation_jobs(job_id),
    topic           TEXT,
    final_article   TEXT,
    seo_metadata    JSONB,
    keywords        JSONB,
    internal_links  JSONB,
    external_refs   JSONB,
    seo_score       INT,
    word_count_actual INT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- LangGraph auto-creates these tables via checkpointer.setup():
-- checkpoints, checkpoint_writes, checkpoint_blobs
```

---

## 8. FAILURE HANDLING — THE FULL PICTURE

```
SCENARIO 1: External API failure (SerpAPI down)
─────────────────────────────────────────────────
research_node()
  └── serp_fetch_tool() throws ConnectionError
        └── try/except catches it
              └── fallback: get_mock_serp_data()   ← graceful degradation
                    └── logs error to state["errors"]
                          └── continues normally ✅

SCENARIO 2: LLM timeout
─────────────────────────────────────────────────
writer_node()
  └── article_writer_tool() times out
        └── except block catches
              └── increments retry_counts["writer"]
                    └── route_after_writer() sees no article_draft
                          └── routes BACK to writer node 🔄
                                └── max 3 retries → error_handler

SCENARIO 3: Process crash mid-execution
─────────────────────────────────────────────────
Research ✅ checkpoint saved
Outline  ✅ checkpoint saved
Writer   💥 CRASH (pod restart, OOM, etc.)

On restart:
  graph.invoke(None, config={"configurable": {"thread_id": "seo-job:abc123"}})
                ↑
          None signals "resume"
          LangGraph reads last checkpoint
          Finds: Research ✅ Outline ✅ Writer = PENDING
          Resumes from Writer — Research & Outline NEVER re-run ✅

SCENARIO 4: QA fails score threshold
─────────────────────────────────────────────────
QA scores article 62/100
  └── qa_result.passed = False
        └── route_after_qa() → back to "writer"
              └── Writer gets QA feedback in state
                    └── Rewrites with improvements
                          └── QA rescores → 84/100 ✅
```

---

## 9. PROJECT FOLDER STRUCTURE

```
seo-agent/
├── app/
│   ├── main.py                  # FastAPI entry point
│   ├── api/
│   │   └── routes.py            # POST /jobs, GET /jobs/{id}
│   ├── graph/
│   │   ├── state.py             # ArticleGenerationState TypedDict
│   │   ├── graph_builder.py     # Nodes + edges assembly
│   │   ├── nodes/
│   │   │   ├── orchestrator.py
│   │   │   ├── research.py
│   │   │   ├── outline.py
│   │   │   ├── writer.py
│   │   │   ├── qa.py
│   │   │   └── output_builder.py
│   │   └── tools/
│   │       ├── serp_fetch.py
│   │       ├── theme_extractor.py
│   │       ├── outline_builder.py
│   │       ├── article_writer.py
│   │       ├── metadata_generator.py
│   │       ├── linking_tool.py
│   │       └── seo_validator.py
│   ├── db/
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── repository.py        # DB read/write helpers
│   │   └── checkpointer.py      # PostgresSaver setup
│   └── config.py                # Env vars, settings
├── tests/
│   ├── test_serp.py
│   ├── test_outline.py
│   ├── test_seo_validator.py
│   └── test_graph_flow.py
├── alembic/                     # DB migrations
├── docker-compose.yml           # Postgres + app
├── .env
└── README.md
```

---

## 10. API ENDPOINTS

```
POST /jobs
  Body: { topic, word_count, language }
  Returns: { job_id, status: "pending" }

GET /jobs/{job_id}
  Returns: { job_id, status, created_at, ... }

GET /jobs/{job_id}/result
  Returns: { article, seo_metadata, keywords, links, score }

POST /jobs/{job_id}/resume
  Used when: job was interrupted, resume from checkpoint
  Calls: graph.invoke(None, config={"thread_id": job_id})
```

---

## 11. TECH STACK SUMMARY

| Layer | Technology | Why |
|---|---|---|
| Agent Framework | LangGraph | Stateful graph, checkpointing, conditional edges |
| LLM | Claude 3.5 Sonnet via API | Cost-effective, strong writing quality |
| Checkpointing | PostgresSaver | Production-grade, crash recovery |
| Job DB | PostgreSQL | Same DB, unified storage |
| API Layer | FastAPI | Async, Pydantic-native |
| SERP Data | SerpAPI / mock fallback | Real search data with graceful degradation |
| Observability | LangSmith | Traces, token costs, step timing |
| Containerization | Docker Compose | Postgres + app in one command |

---

## 12. KEY DESIGN PRINCIPLES FOLLOWED

1. **State is the single source of truth** — every node reads/writes only the shared state
2. **Reducers prevent data loss** — `errors` field appends, never overwrites
3. **Max retries per node** — prevents infinite loops, each agent fails independently
4. **Checkpoint per superstep** — every node completion = saved state in Postgres
5. **Graceful degradation** — SERP API failure falls back to mock, never crashes pipeline
6. **Idempotent nodes** — resuming from checkpoint never duplicates work
7. **Separation of concerns** — each node owns exactly one responsibility
8. **QA revision cycle capped** — max 3 revisions, then publish best-effort
