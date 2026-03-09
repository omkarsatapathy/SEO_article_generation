# SEO Article Generation System

A production-ready, multi-agent LangGraph pipeline that generates fully SEO-optimised articles from a topic string. Backed by FastAPI, PostgreSQL persistence, and programmatic QA scoring.

---

## Architecture

```
INPUT:  { topic, word_count, language }
          ↓
  ┌─────────────────────┐
  │   FastAPI Gateway   │  ← Creates job_id, fires BackgroundTask
  └────────┬────────────┘
           ↓
  ┌─────────────────────┐
  │  LangGraph Graph    │  ← Compiled StateGraph
  │                     │
  │  [ORCHESTRATOR]     │  ← Validates inputs, assigns job_id
  │       ↓             │
  │  [RESEARCH AGENT]   │  ← SERP fetch + theme extraction
  │       ↓             │
  │  [OUTLINE AGENT]    │  ← H1/H2/H3 structure builder
  │       ↓             │
  │  [WRITER AGENT]     │  ← Full article + metadata + links
  │       ↓             │
  │  [QA AGENT]         │  ← Programmatic SEO scoring (0-100)
  │       ↓             │
  │  [OUTPUT BUILDER]   │  ← Final structured output
  └─────────────────────┘
           ↓
  ┌─────────────────────┐
  │   PostgreSQL DB     │  ← Checkpoints + job tracking
  └─────────────────────┘
           ↓
OUTPUT: { article, seo_metadata, keywords, links, score }
```

---

## Design Decisions

**Why LangGraph?**  
The generation pipeline is inherently stateful and multi-step. LangGraph's `StateGraph` gives us typed shared state, conditional routing (retry loops, QA revision cycles), and first-class support for PostgreSQL checkpointing — so a crashed job can be resumed from where it left off without re-running completed nodes.

**Why Pydantic-enforced tool outputs?**  
All LLM-powered tools use `llm.with_structured_output(PydanticModel)` rather than raw `llm.invoke()`. This eliminates hallucinated field names, wrong types, and missing keys at the source. Every tool return is validated before it enters the shared state.

**Why a QA revision loop?**  
Generating an article and immediately publishing it produces unreliable SEO quality. The QA node runs 10 programmatic checks (keyword density, H1/H2 coverage, word count, metadata length, heading hierarchy, etc.) and scores the article 0–100. If the score is below `QA_PASS_SCORE` (default 80), the article is sent back to the writer with the specific issues attached — up to 3 revision cycles before best-effort publishing.

**Why PostgresSaver for durability?**  
LLM pipelines are slow (30–90 s per run). Using `PostgresSaver` as the LangGraph checkpointer means every node completion is checkpointed to Postgres. If the server restarts mid-pipeline, `POST /jobs/{id}/resume` replays from the last successful node without any wasted LLM calls.

---

## Setup Instructions

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd SEO_article_generation
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and fill in OPENAI_API_KEY (required)
   # SERPAPI_KEY is optional — mock data is used if absent
   ```

3. **Start services with Docker Compose**
   ```bash
   docker-compose up -d
   ```
   The `app` service waits for Postgres to pass its healthcheck before starting.

4. **API available at** `http://localhost:8000`

5. **Interactive Swagger docs at** `http://localhost:8000/docs`

---

## API Usage

### Create a generation job
```bash
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -d '{"topic": "best productivity tools for remote teams", "word_count": 1500}'
```
```json
{"job_id": "a1b2c3d4-...", "status": "pending"}
```

### Poll job status
```bash
curl http://localhost:8000/jobs/a1b2c3d4-...
```
```json
{
  "job_id": "a1b2c3d4-...",
  "topic": "best productivity tools for remote teams",
  "status": "writing",
  "seo_score": null,
  "created_at": "2026-03-07T10:00:00+00:00",
  "updated_at": "2026-03-07T10:00:45+00:00",
  "error_message": null
}
```

### Retrieve completed article
```bash
curl http://localhost:8000/jobs/a1b2c3d4-.../result
```

### Resume a failed or interrupted job
```bash
curl -X POST http://localhost:8000/jobs/a1b2c3d4-.../resume
```

### List all jobs
```bash
curl "http://localhost:8000/jobs/?limit=10&offset=0"
```

---

## Example Input → Output

**Input**
```json
{
  "topic": "best productivity tools for remote teams",
  "word_count": 1500
}
```

**Output** (`GET /jobs/{id}/result`)
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "topic": "best productivity tools for remote teams",
  "article": "# Best Productivity Tools for Remote Teams\n\nRemote teams rely on the right productivity tools to stay connected, aligned, and efficient. In this comprehensive guide, we cover the top-rated solutions used by leading distributed companies in 2026 — from project management platforms to async communication hubs...\n\n[...truncated]",
  "seo_metadata": {
    "title_tag": "Best Productivity Tools for Remote Teams 2026",
    "meta_description": "Discover the top productivity tools for remote teams. Compare features, pricing, and use cases to boost your distributed team's output today.",
    "primary_keyword": "productivity tools for remote teams",
    "secondary_keywords": [
      "remote collaboration software",
      "project management tools",
      "async communication tools",
      "team productivity apps"
    ]
  },
  "keywords": [
    {"word": "productivity tools for remote teams", "frequency": 12, "is_primary": true},
    {"word": "remote collaboration software", "frequency": 7, "is_primary": false},
    {"word": "project management tools", "frequency": 5, "is_primary": false}
  ],
  "internal_links": [
    {"anchor_text": "remote work best practices", "suggested_target_topic": "remote work guide"},
    {"anchor_text": "team communication tools", "suggested_target_topic": "communication software comparison"},
    {"anchor_text": "project management software", "suggested_target_topic": "project management tools review"}
  ],
  "external_references": [
    {"source_url": "https://hbr.org/topic/remote-work", "context": "In the intro when citing remote work adoption statistics"},
    {"source_url": "https://www.forbes.com/advisor/business/software/best-project-management-software/", "context": "In the project management section for third-party validation"}
  ],
  "seo_score": 87,
  "word_count_actual": 1523
}
```

---

## Running Tests

```bash
pytest tests/ -v
```

The test suite covers:
- SERP fetch tool with mock fallback (`tests/test_serp.py`)
- SEO validator all 10 checks (`tests/test_seo_validator.py`)
- Graph compilation and conditional routing (`tests/test_graph_flow.py`)
- Full pipeline integration with mocked LLM calls (`tests/test_graph_flow.py::test_full_pipeline_with_mock_serp`)

