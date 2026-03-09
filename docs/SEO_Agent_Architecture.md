# SEO Article Generation System
### Multi-Agent LangGraph Pipeline · FastAPI · PostgreSQL · Real-time SSE Logs

---

## 1. SYSTEM OVERVIEW

```
╔══════════════════════════════════════════════════════════════════════╗
║  INPUT  { topic, word_count, language }                              ║
╚══════════════════════════════════════════════════════════════════════╝
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │         FastAPI Gateway             │
        │  POST /jobs/  →  202 Accepted       │
        │  Creates UUID job_id, starts BG     │
        │  task in asyncio.to_thread()        │
        └──────────────┬──────────────────────┘
                       │
                       ▼
        ╔══════════════════════════════════════╗
        ║       LangGraph StateGraph           ║
        ║                                      ║
        ║  START ──► ORCHESTRATOR              ║
        ║                │                     ║
        ║                ▼                     ║
        ║  ┌────── RESEARCH ◄─────────┐        ║
        ║  │  success   │  fail retry │        ║
        ║  │            └─────────────┘        ║
        ║  ▼              (max 3 retries)      ║
        ║  ┌────── OUTLINE  ◄─────────┐        ║
        ║  │  success   │  fail retry │        ║
        ║  │            └─────────────┘        ║
        ║  ▼              (max 3 retries)      ║
        ║  ┌────── WRITER   ◄─────────┐───┐    ║
        ║  │  success   │  fail retry │   |    ║
        ║  │            └─────────────┘   |    ║
        ║  │              (max 3 retries) |    ║
        ║  │                              |    ║
        ║  ▼    │  QA fail: score < 80    |    ║
        ║  QA ──┘  → back to WRITER ──────┘    ║
        ║  │         (max 3 revisions)         ║
        ║  │ QA pass OR max revisions          ║
        ║  ▼                                   ║
        ║  OUTPUT BUILDER ──► END              ║
        ║                                      ║
        ║  (any node hits max retries) │       ║
        ║    └──► ERROR HANDLER ──► END        ║
        ╚══════════════════════════════════════╝
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
  ┌───────────────┐       ┌─────────────────────┐
  │  SQLAlchemy   │       │  PostgresSaver      │
  │  ORM (async)  │       │  Checkpoint Store   │
  │               │       │                     │
  │ generation_   │       │  checkpoints        │
  │   jobs        │       │  checkpoint_writes  │
  │ generated_    │       │  checkpoint_blobs   │
  │   articles    │       └─────────────────────┘
  └───────────────┘
          │
          ▼
╔══════════════════════════════════════════════════════════════════════╗
║  OUTPUT  { final_article, seo_metadata, keywords, links, score }     ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## 2. NODE CATALOGUE

Each node in the graph is a **ReAct agent** (using `create_react_agent`) except the Writer, which runs tools sequentially for precise control over section-by-section generation.

```
┌──────────────────┬─────────────────┬────────────────────────────────────────────┬───────────────────┐
│  Node            │  Type           │  Tools                                     │  Max Iterations   │
├──────────────────┼─────────────────┼────────────────────────────────────────────┼───────────────────┤
│  ORCHESTRATOR    │  ReAct Agent    │  validate_input_tool                       │  10               │
│                  │                 │  job_init_tool                             │                   │
├──────────────────┼─────────────────┼────────────────────────────────────────────┼───────────────────┤
│  RESEARCH        │  ReAct Agent    │  serp_fetch_tool                           │  10               │
│                  │                 │  theme_extractor_tool                      │                   │
│                  │                 │  faq_extractor_tool  (heuristic, no LLM)   │                   │
├──────────────────┼─────────────────┼────────────────────────────────────────────┼───────────────────┤
│  OUTLINE         │  ReAct Agent    │  outline_builder_tool                      │  10               │
│                  │                 │  keyword_mapper_tool (heuristic, no LLM)   │                   │
├──────────────────┼─────────────────┼────────────────────────────────────────────┼───────────────────┤
│  WRITER          │  Sequential     │  article_writer_tool                       │  N/A              │
│                  │  (direct calls) │  linking_tool                              │                   │
│                  │                 │  metadata_generator_tool                   │                   │
├──────────────────┼─────────────────┼────────────────────────────────────────────┼───────────────────┤
│  QA              │  ReAct Agent    │  seo_validator_tool                        │  8                │
│                  │                 │  score_calculator_tool (penalty/bonus)     │                   │
├──────────────────┼─────────────────┼────────────────────────────────────────────┼───────────────────┤
│  OUTPUT BUILDER  │  Plain function │  —  (assembly + references merge only)    │  N/A               │
├──────────────────┼─────────────────┼────────────────────────────────────────────┼───────────────────┤
│  ERROR HANDLER   │  Plain function │  —  (terminal node, sets status=failed)   │  N/A               │
└──────────────────┴─────────────────┴────────────────────────────────────────────┴───────────────────┘
```

---

## 3. CONDITIONAL ROUTING LOGIC

```
┌────────────────────────────────────────────────────────────────────────────┐
│                       ROUTING DECISION TABLE                               │
├───────────────┬──────────────────────────────┬────────────────────────────-┤
│  After Node   │  Condition                   │  Destination                │
├───────────────┼──────────────────────────────┼─────────────────────────────┤
│  RESEARCH     │  retry_counts["research"]    │  error_handler              │
│               │    >= MAX_RETRIES (3)        │                             │
│               │  serp_results present        │  outline                    │
│               │  (else)                      │  research  ← retry          │
├───────────────┼──────────────────────────────┼─────────────────────────────┤
│  OUTLINE      │  retry_counts["outline"]     │  error_handler              │
│               │    >= MAX_RETRIES (3)        │                             │
│               │  outline present             │  writer                     │
│               │  (else)                      │  outline   ← retry          │
├───────────────┼──────────────────────────────┼─────────────────────────────┤
│  WRITER       │  retry_counts["writer"]      │  error_handler              │
│               │    >= MAX_RETRIES (3)        │                             │
│               │  article_draft present       │  qa                         │
│               │  (else)                      │  writer    ← retry          │
├───────────────┼──────────────────────────────┼─────────────────────────────┤
│  QA           │  status == "done"            │  output                     │
│               │  revision_count              │  output  (best-effort pub.) │
│               │    >= MAX_REVISIONS (3)      │                             │
│               │  (else — score too low)      │  writer   ← revision loop   │
└───────────────┴──────────────────────────────┴─────────────────────────────┘
```

> The QA → Writer loop passes accumulated `qa_result.issues` and `qa_result.suggestions`
> directly in state so the Writer receives first-class feedback on each revision cycle.


**Key design decisions:**

| Decision | Reason |
|---|---|
| `Annotated[List[str], operator.add]` on `errors` | Every node appends errors; nothing gets clobbered |
| All stage fields Optional | Nodes only populate what they own; safe for partial states |
| `revision_count` int | Caps the QA → Writer revision loop cleanly |
| `SeoMetadata` auto-truncation validators | LLM output violating char limits is fixed silently |
| `CompetitorStructure` Pydantic model | Typed headings list instead of raw `dict` |
| `OutlineOutput` wrapper | `with_structured_output` requires an object, not a bare list |

---

## 5. POSTGRESQL — TWO SEPARATE LAYERS

The system uses PostgreSQL for two distinct purposes with separate code paths:

```
┌────────────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                             │
│                                                                    │
│  ┌──────────────────────────────┐  ┌────────────────────────────┐  │
│  │   SQLAlchemy Async ORM       │  │   LangGraph PostgresSaver  │  │
│  │   (app/db/)                  │  │   (app/db/checkpointer.py) │  │
│  │                              │  │                            │  │
│  │  generation_jobs             │  │  checkpoints               │  │
│  │  ├─ job_id  UUID PK          │  │  checkpoint_writes         │  │
│  │  ├─ topic   TEXT             │  │  checkpoint_blobs          │  │
│  │  ├─ word_count INT           │  │                            │  │
│  │  ├─ language VARCHAR(10)     │  │  thread_id links back to   │  │
│  │  ├─ status  VARCHAR(20)      │  │  generation_jobs.thread_id │  │
│  │  ├─ thread_id TEXT UNIQUE    │  │                            │  │
│  │  ├─ error_message TEXT       │  │  Key: "seo-job:{job_id}"   │  │
│  │  ├─ seo_score INT            │  └────────────────────────────┘  │
│  │  └─ timestamps               │                                  │
│  │                              │                                  │
│  │  generated_articles          │                                  │
│  │  ├─ id        UUID PK        │                                  │
│  │  ├─ job_id    UUID FK        │                                  │
│  │  ├─ final_article TEXT       │                                  │
│  │  ├─ seo_metadata  JSON       │                                  │
│  │  ├─ keywords      JSON       │                                  │
│  │  ├─ internal_links JSON      │                                  │
│  │  ├─ external_refs  JSON      │                                  │
│  │  ├─ seo_score  INT           │                                  │
│  │  └─ word_count_actual INT    │                                  │
│  └──────────────────────────────┘                                  │
└────────────────────────────────────────────────────────────────────┘
```

**Checkpointing setup** (`app/db/checkpointer.py`):
```python
pool = ConnectionPool(conninfo=db_url, max_size=10, kwargs={"autocommit": True})
with pool.connection() as conn:
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()     # creates the three checkpoint tables once
```

**Crash resume pattern:**
```
Pipeline: Research ✅ → Outline ✅ → Writer 💥 CRASH

On restart — pass None as input to signal "resume":
  graph.invoke(None, config={"configurable": {"thread_id": "seo-job:abc123"}})

LangGraph finds the last checkpoint → skips Research + Outline → retries Writer only.
```

> **Note:** The background pipeline currently runs with `checkpointer=None` (in-memory only).
> `get_checkpointer()` and `_resume_pipeline()` are wired and ready — enabling full
> crash-durability is a one-line change in `_run_pipeline`.

---

## 6. API LAYER

```
┌────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                          │
│                        (app/main.py)                               │
│                                                                     │
│  Router: /jobs  ─────────────────────────────────────────────────  │
│                                                                     │
│  POST  /jobs/                                                       │
│    Body: { topic, word_count?, language? }                          │
│    → Creates GenerationJob row (status=pending)                     │
│    → Spawns asyncio.to_thread(graph.invoke, ...) background task   │
│    → Returns 202 { job_id }                                         │
│                                                                     │
│  GET   /jobs/{job_id}                                               │
│    → Returns JobStatusResponse { job_id, status, seo_score, ... }  │
│                                                                     │
│  GET   /jobs/{job_id}/result                                        │
│    → Returns ArticleResultResponse:                                 │
│       { article, seo_metadata, keywords, internal_links,           │
│         external_references, seo_score, word_count_actual }        │
│                                                                     │
│  POST  /jobs/{job_id}/resume                                        │
│    → Resumes interrupted pipeline from last LangGraph checkpoint    │
│                                                                     │
│  Router: /logs  ─────────────────────────────────────────────────  │
│                                                                     │
│  GET   /logs/stream                                                 │
│    → Server-Sent Events (SSE) — real-time log streaming            │
│    → Replays ring-buffer (last 400 entries) on connect             │
│    → Broadcasts every log.INFO+ record from the entire process     │
│    → Keep-alive ping every 20 s                                     │
│                                                                     │
│  GET   /health  →  { "status": "healthy" }                         │
└────────────────────────────────────────────────────────────────────┘
```

**Why `asyncio.to_thread` for the graph?**

The LangGraph graph is synchronous. Running it directly would block the asyncio event loop, preventing SSE clients (`/logs/stream`) from receiving live log updates during article generation. `asyncio.to_thread` offloads the graph to a thread pool, keeping the event loop free.

---

## 7. REAL-TIME LOG STREAMING (SSE)

```
app/api/log_stream.py

  _BroadcastHandler (logging.Handler)
        │
        │  attaches to logging.getLogger() root
        │  captures EVERY log record process-wide
        │
        ▼
  _buffer: deque(maxlen=400)   ← ring buffer, newest evicts oldest
        │
        ├──► _queues: List[asyncio.Queue]   ← one Queue per SSE client
        │
        └──► loop.call_soon_threadsafe()    ← safe delivery from sync threads

  GET /logs/stream  (StreamingResponse)
    1. Replays entire _buffer to new client (catch-up)
    2. Listens on personal Queue with 20s timeout
    3. Sends each entry as SSE event:
         data: {"level": "INFO", "name": "app.graph.nodes.writer", "text": "..."}
    4. Sends ": keep-alive" if no events for 20s
    5. Removes Queue on disconnect
```

---

## 8. QA SCORING SYSTEM

The QA agent runs `seo_validator_tool` (programmatic checks) and `score_calculator_tool` (penalty/bonus adjuster), then decides pass/fail.

```
Starting score: 100

Penalty catalogue (from hyperparams.yaml)
──────────────────────────────────────────────────────────────────────
  - keyword_in_h1                  −15  primary keyword absent from H1
  - keyword_in_intro               −15  absent from first 500 chars of body
  - keyword_density_out_of_range   −10  density < 0.5% or > 3.0%
  - keyword_stuffing               −10  additional density penalty
  - h2_keyword_coverage            −10  fewer than 2 H2s contain a keyword
  - word_count_marginal            −10  75–85% or 115–150% of target
  - word_count_significant         −20  60–75% of target
  - word_count_severe              −30  < 60% or > 200% of target
  - title_tag_length               −10  title_tag > 60 chars
  - meta_description_length        −10  meta_description > 160 chars
  - heading_hierarchy              −10  H3 without parent H2 etc.
  - short_section                  − 5  H2 section < 100 words
  - link_placeholders              − 5  unresolved "[LINK]" markers in text
  - content_truncated              − 5  article ends mid-sentence
──────────────────────────────────────────────────────────────────────

Pass threshold: score ≥ 80

If score < 80 AND revision_count < max_revisions (3):
  → Route back to WRITER with qa_result in state

If score < 80 AND revision_count >= max_revisions:
  → Route to OUTPUT BUILDER (publish best-effort)
```

---

## 9. OUTPUT BUILDER

The Output Builder is a plain function (no LLM, no agent). Its job is final assembly:

```
1. Prefer final_article; fall back to article_draft
2. Build References section:
   a. Pull from external_references (agent-picked authoritative sources) first
   b. Fill remaining slots from serp_results (sorted by rank)
   c. Deduplicate by URL; cap at 5 links
   d. Append as Markdown: "## References\n1. [title](url)"
3. Log completion banner with word count, SEO score, job_id
4. Return { final_article, status: "done", updated_at }
```

---

## 10. CONFIGURATION SYSTEM

Three YAML files under `config/` provide all tuneable parameters:

```
config/
├── hyperparams.yaml   ← all numerical thresholds, limits, word-count targets
├── settings.yaml      ← app title, version, CORS origins, logging format
└── prompts.yaml       ← agent system prompts (one per node)
```

Accessed via a unified `cfg` object:

```python
cfg.hyperparams.pipeline.max_retries        # 3
cfg.hyperparams.pipeline.max_revisions      # 3
cfg.hyperparams.article.word_count_default  # 1500
cfg.hyperparams.qa.pass_score               # 80
cfg.hyperparams.agent.research_max_iterations  # 10
cfg.prompts.agents.research                 # system prompt string
cfg.settings.app.title                      # "SEO Article Generation API"
```

**Key hyperparameters at a glance:**

| Parameter | Value | Description |
|---|---|---|
| `pipeline.max_retries` | 3 | Max retries per node before error_handler |
| `pipeline.max_revisions` | 3 | Max QA→Writer revision cycles |
| `pipeline.default_word_count` | 1500 | Default article length |
| `qa.pass_score` | 80 | Minimum SEO score to pass QA |
| `article.word_count_min` | 500 | API input validation floor |
| `article.word_count_max` | 5000 | API input validation ceiling |
| `writing.word_count_ceiling_multiplier` | 1.15 | Hard upper cap = target × 1.15 |
| `qa.thresholds.keyword_density_min` | 0.5% | Under-optimised threshold |
| `qa.thresholds.keyword_density_max` | 3.0% | Keyword stuffing threshold |

---

## 11. PROJECT STRUCTURE

```
SEO_article_generation/
│
├── app/
│   ├── main.py                     FastAPI entry point, CORS, lifespan
│   ├── config.py                   Env var settings (DATABASE_URL, etc.)
│   │
│   ├── api/
│   │   ├── routes.py               REST endpoints (/jobs/*)
│   │   └── log_stream.py           SSE log broadcast (/logs/stream)
│   │
│   ├── graph/
│   │   ├── state.py                ArticleGenerationState + all sub-models
│   │   ├── graph_builder.py        build_graph() + all routing functions
│   │   │
│   │   ├── nodes/
│   │   │   ├── orchestrator.py     ReAct agent: validate_input + job_init
│   │   │   ├── research.py         ReAct agent: serp_fetch + theme + faq
│   │   │   ├── outline.py          ReAct agent: outline_builder + kw_mapper
│   │   │   ├── writer.py           Sequential: article + linking + metadata
│   │   │   ├── qa.py               ReAct agent: seo_validator + score_calc
│   │   │   └── output_builder.py   Plain fn: assembly + references merge
│   │   │
│   │   └── tools/
│   │       ├── serp_fetch.py
│   │       ├── theme_extractor.py
│   │       ├── outline_builder.py
│   │       ├── article_writer.py
│   │       ├── metadata_generator.py
│   │       ├── linking_tool.py
│   │       └── seo_validator.py
│   │
│   └── db/
│       ├── models.py               SQLAlchemy ORM: GenerationJob + GeneratedArticle
│       ├── repository.py           Async CRUD: create/get/update job, save article
│       └── checkpointer.py         PostgresSaver pool setup
│
├── config/
│   ├── config.py                   Unified cfg loader (merges all YAMLs)
│   ├── hyperparams.yaml            Numerical limits and thresholds
│   ├── settings.yaml               App settings and CORS
│   └── prompts.yaml                Agent system prompts
│
├── tests/
│   ├── conftest.py
│   ├── test_serp.py
│   ├── test_outline.py
│   ├── test_coerce_links.py
│   ├── test_seo_validator.py
│   └── test_graph_flow.py
│
├── GUI/
│   └── index.html                  Simple browser UI
│
├── docs/                           Architecture diagrams (HTML)
├── Dockerfile
├── docker-compose.yml              App + PostgreSQL in one command
├── pyproject.toml
└── requirements.txt
```

---

## 12. TECH STACK

| Layer | Technology | Role |
|---|---|---|
| Agent framework | LangGraph | Stateful graph, conditional edges, checkpointing |
| LLM | Configurable via `get_llm()` | Article generation, theme extraction, QA |
| API | FastAPI (async) | REST endpoints + SSE log stream |
| ORM | SQLAlchemy async + asyncpg | Job tracking and article persistence |
| Checkpointing | LangGraph PostgresSaver | Crash-recovery state snapshots |
| Database | PostgreSQL | ORM tables + checkpoint tables |
| Validation | Pydantic v2 | All agent inputs/outputs, API models |
| Configuration | YAML + dataclasses | Decoupled hyperparams, prompts, settings |
| SERP data | SerpAPI + mock fallback | Real search data with graceful degradation |
| Containerisation | Docker + Compose | Reproducible dev/prod environment |

---

## 13. KEY DESIGN PRINCIPLES

```
1. STATE IS THE SINGLE SOURCE OF TRUTH
   Every node reads from and writes to ArticleGenerationState only.
   No global variables, no side-channel communication.

2. APPEND-ONLY ERROR REDUCER
   errors: Annotated[List[str], operator.add]
   Any node can log failures without erasing previous errors.

3. INDEPENDENT PER-NODE RETRY BUDGETS
   retry_counts["research/outline/writer/qa"] — each agent
   fails independently; one retry doesn't penalise another.

4. QA REVISION LOOP WITH A HARD CEILING
   max_revisions = 3. After that, publish best-effort.
   Prevents infinite writer↔qa cycles.

5. PYDANTIC VALIDATORS AS SAFETY NETS
   SeoMetadata auto-truncates over-length strings.
   QAResult score is range-clamped. No crashes on LLM drift.

6. WRITER IS SEQUENTIAL, NOT ReAct
   article_writer → linking_tool → metadata_generator in order.
   Deterministic section-by-section generation; agent loop adds
   no value here and risks non-determinism.

7. SSE + asyncio.to_thread FOR NON-BLOCKING OBSERVABILITY
   Graph runs in a thread pool. Event loop stays free.
   Connected browsers see live logs while pipeline runs.

8. TWO DB LAYERS, ONE DATABASE
   SQLAlchemy ORM owns job/article records.
   PostgresSaver owns checkpoint blobs.
   Same Postgres instance, cleanly separated schemas.
```
