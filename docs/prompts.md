# SEO Article Generation — 10 Sequential Implementation Prompts

> Each prompt builds on the output of the previous one. No task is repeated.
> Copy-paste each prompt in sequence to your AI coding assistant or follow manually.

---

## Prompt 1: Project Scaffolding & Dependencies

```
Create the project structure for an SEO article generation system at the current directory.

Create these exact files and directories:
  app/
    __init__.py
    main.py              (empty FastAPI app placeholder — just app = FastAPI() with title and version)
    config.py            (Pydantic BaseSettings loading from .env: OPENAI_API_KEY, SERPAPI_KEY, DATABASE_URL defaulting to "postgresql://user:pass@localhost:5432/seo_agent", LLM_MODEL defaulting to "gpt-4o", MAX_RETRIES defaulting to 3, QA_PASS_SCORE defaulting to 80)
    api/
      __init__.py
      routes.py          (empty file — placeholder)
    graph/
      __init__.py
      state.py           (empty file — placeholder)
      graph_builder.py   (empty file — placeholder)
      nodes/
        __init__.py
        orchestrator.py  (empty)
        research.py      (empty)
        outline.py       (empty)
        writer.py        (empty)
        qa.py            (empty)
        output_builder.py (empty)
      tools/
        __init__.py
        serp_fetch.py    (empty)
        theme_extractor.py (empty)
        outline_builder.py (empty)
        article_writer.py (empty)
        metadata_generator.py (empty)
        linking_tool.py  (empty)
        seo_validator.py (empty)
    db/
      __init__.py
      models.py          (empty)
      repository.py      (empty)
      checkpointer.py    (empty)
  tests/
    __init__.py
    conftest.py          (empty)
    test_serp.py         (empty)
    test_outline.py      (empty)
    test_seo_validator.py (empty)
    test_graph_flow.py   (empty)
  .env.example           (template with all required env vars as KEY=placeholder)
  requirements.txt       (fastapi, uvicorn[standard], langgraph>=0.2.0, langchain-openai, langchain-core, psycopg[binary,pool], langgraph-checkpoint-postgres, pydantic>=2.0, python-dotenv, requests, sqlalchemy[asyncio], asyncpg, alembic, httpx, pytest, pytest-asyncio)
  docker-compose.yml     (PostgreSQL 16 service with volume, port 5432, env vars matching .env.example)
  README.md              (Project title + "Setup instructions coming soon")

Do NOT implement any logic yet — only create the skeleton files with proper imports and placeholders.
```

---

## Prompt 2: Pydantic State Schema & Data Models

```
Implement the complete Pydantic data models and LangGraph state schema.

File: app/graph/state.py

Define ALL these Pydantic BaseModel classes:
1. SerpResult(BaseModel): rank (int), url (str), title (str), snippet (str)
2. Keyword(BaseModel): word (str), frequency (int), is_primary (bool)
3. OutlineSection(BaseModel): level (str — "H1"/"H2"/"H3"), heading (str), keywords (List[str]), word_target (int)
4. InternalLink(BaseModel): anchor_text (str), suggested_target_topic (str)
5. ExternalReference(BaseModel): source_url (str), context (str — where in article to place this)
6. SeoMetadata(BaseModel): title_tag (str, max 60 chars with Pydantic field validator), meta_description (str, max 160 chars with validator), primary_keyword (str), secondary_keywords (List[str])
7. QAResult(BaseModel): score (int, ge=0, le=100), passed (bool), issues (List[str]), suggestions (List[str])
8. ThemeAnalysis(BaseModel): themes (List[str]), keywords (List[Keyword]), competitor_structures (List[dict]), faqs (List[str])
9. ArticleDraft(BaseModel): content (str), word_count (int), sections_written (int)
10. OutlineOutput(BaseModel): sections (List[OutlineSection])
11. LinkingSuggestions(BaseModel): internal (List[InternalLink]), external (List[ExternalReference])

Then define the LangGraph shared state as TypedDict:
12. ArticleGenerationState(TypedDict):
    - job_id: str
    - topic: str
    - word_count: int
    - language: str
    - status: str  (pending | researching | outlining | writing | qa | done | failed)
    - created_at: str
    - updated_at: str
    - serp_results: Optional[List[SerpResult]]
    - common_themes: Optional[List[str]]
    - extracted_keywords: Optional[List[Keyword]]
    - competitor_structures: Optional[List[dict]]
    - faq_questions: Optional[List[str]]
    - outline: Optional[List[OutlineSection]]
    - article_draft: Optional[str]
    - revision_count: int
    - qa_result: Optional[QAResult]
    - final_article: Optional[str]
    - seo_metadata: Optional[SeoMetadata]
    - internal_links: Optional[List[InternalLink]]
    - external_references: Optional[List[ExternalReference]]
    - errors: Annotated[List[str], operator.add]  (append-only reducer)
    - retry_counts: dict  ({"research": 0, "outline": 0, "writer": 0, "qa": 0})

File: app/db/models.py

Define SQLAlchemy ORM models using DeclarativeBase:
1. GenerationJob: job_id (UUID PK), topic (Text), word_count (Integer), language (String(10)), status (String(20)), thread_id (Text, unique), error_message (Text nullable), seo_score (Integer nullable), created_at (DateTime with timezone), updated_at (DateTime with timezone)
2. GeneratedArticle: id (UUID PK), job_id (UUID FK to GenerationJob), topic (Text), final_article (Text), seo_metadata (JSON), keywords (JSON), internal_links (JSON), external_refs (JSON), seo_score (Integer), word_count_actual (Integer), created_at (DateTime with timezone)

Do NOT implement any node logic or tools — only the data models and state.
```

---

## Prompt 3: Database Layer — PostgreSQL Checkpointer & Repository

```
Implement the database layer: connection pool, LangGraph checkpointer, and CRUD repository.

File: app/db/checkpointer.py
- Import PostgresSaver from langgraph.checkpoint.postgres
- Import ConnectionPool from psycopg_pool
- Create a function `get_checkpointer(db_url: str) -> PostgresSaver` that:
  1. Creates a ConnectionPool with max_size=10, kwargs={"autocommit": True}
  2. Gets a connection from the pool
  3. Creates PostgresSaver with that connection
  4. Calls checkpointer.setup() to create checkpoint tables
  5. Returns the checkpointer
- Also export a `get_pool(db_url: str) -> ConnectionPool` function for reuse
- Make it work with the config.py settings.DATABASE_URL

File: app/db/repository.py
- Import the SQLAlchemy models from models.py
- Use async SQLAlchemy with asyncpg (create_async_engine, async_sessionmaker)
- Implement the JobRepository class with these async methods:
  1. create_job(topic: str, word_count: int, language: str) -> GenerationJob
     - Generates UUID, sets status="pending", creates thread_id as "seo-job:{job_id}"
     - Saves to DB and returns the model
  2. get_job(job_id: UUID) -> Optional[GenerationJob]
  3. update_job_status(job_id: UUID, status: str, seo_score: Optional[int] = None, error_message: Optional[str] = None)
     - Also updates updated_at timestamp
  4. save_article(job_id: UUID, article_data: dict) -> GeneratedArticle
     - Accepts the final output dict and maps it to GeneratedArticle columns
  5. get_article(job_id: UUID) -> Optional[GeneratedArticle]
  6. list_jobs(limit: int = 20, offset: int = 0) -> List[GenerationJob]
- Implement get_async_engine(db_url: str) and get_session_factory() as module-level helpers
- Add an async init_db() function that creates all tables using metadata.create_all

Do NOT implement API routes, graph nodes, or tools.
```

---

## Prompt 4: SERP Fetch Tool & Mock Data

```
Implement the SERP fetch tool with SerpAPI integration and realistic mock data fallback.

File: app/graph/tools/serp_fetch.py
- Import SerpResult from app.graph.state
- Import settings from app.config
- Implement the serp_fetch_tool as a LangChain @tool:
  - Input: query (str)
  - Output: List[SerpResult] — Pydantic-validated
  - Primary path: Call SerpAPI (https://serpapi.com/search) with params q=query, num=10, api_key from settings
  - Parse the response JSON: extract organic_results, map each to SerpResult(rank=position, url=link, title=title, snippet=snippet)
  - Validate each result with SerpResult(**data) before returning
  - On ANY exception (ConnectionError, KeyError, Timeout): fall back to get_mock_serp_data(query)
  - Log the fallback with a warning

- Implement get_mock_serp_data(query: str) -> List[SerpResult]:
  - Generate 10 realistic mock results based on the query topic
  - Use varied, realistic URLs (mix of big sites like Forbes, HubSpot, TechCrunch, etc.)
  - Each mock result must have: rank 1-10, realistic URL, keyword-rich title, 150-char snippet
  - Create 3 different template sets for variety (tech topics, marketing topics, general topics)
  - Select the template based on simple keyword detection in the query
  - Return as List[SerpResult] — Pydantic-validated

File: tests/test_serp.py
- Write 4 tests:
  1. test_mock_serp_returns_10_results: Call get_mock_serp_data with a topic, assert len == 10
  2. test_mock_serp_results_are_valid_pydantic: Assert each result is a SerpResult instance with all fields populated
  3. test_mock_serp_ranks_sequential: Assert ranks are 1 through 10
  4. test_serp_fetch_falls_back_to_mock: Mock requests.get to raise ConnectionError, assert serp_fetch_tool still returns 10 valid results

Do NOT implement any other tools, nodes, or the graph.
```

---

## Prompt 5: LLM-Powered Tools — Theme Extractor, Outline Builder, Article Writer, Metadata Generator, Linking Tool

```
Implement ALL 5 LLM-powered tools using llm.with_structured_output() for Pydantic-enforced returns.

Setup: Create a shared LLM instance helper.
File: app/graph/tools/__init__.py
- Import ChatOpenAI from langchain_openai
- Import settings from app.config
- Create get_llm() function that returns ChatOpenAI(model=settings.LLM_MODEL, temperature=0.7)

File: app/graph/tools/theme_extractor.py
- @tool function: theme_extractor_tool(serp_results_json: str) -> str
  - Note: LangChain tools serialize I/O as strings, so accept JSON string input
  - Parse the input JSON into List[SerpResult]
  - Use structured_llm = get_llm().with_structured_output(ThemeAnalysis)
  - Prompt the LLM to analyze the 10 SERP results and extract: top 5 themes, primary + 5-8 secondary keywords with frequency estimates, competitor heading structures, FAQ questions
  - Return the ThemeAnalysis result serialized as JSON string
  - Wrap in try/except — on failure, return a minimal ThemeAnalysis with topic as only theme

File: app/graph/tools/outline_builder.py
- @tool function: outline_builder_tool(themes_json: str, keywords_json: str, word_count: int) -> str
  - Use structured_llm = get_llm().with_structured_output(OutlineOutput)
  - Prompt: Build SEO article outline with H1 (1), H2s (4-6) one per theme, H3s (2-3 per H2)
  - Distribute word_count proportionally across sections
  - Assign relevant keywords to each section
  - Return OutlineOutput serialized as JSON string

File: app/graph/tools/article_writer.py
- @tool function: article_writer_tool(outline_json: str, keywords_json: str, themes_json: str, language: str, faq_questions_json: str) -> str
  - Use structured_llm = get_llm().with_structured_output(ArticleDraft)
  - Prompt: Write complete SEO article following the outline exactly
  - Requirements in prompt: natural human tone, primary keyword in H1 + first paragraph, keyword density 1-2%, proper markdown headings, FAQ section at end, match word targets per section
  - Return ArticleDraft serialized as JSON string

File: app/graph/tools/metadata_generator.py
- @tool function: metadata_generator_tool(article_content: str, primary_keyword: str) -> str
  - Use structured_llm = get_llm().with_structured_output(SeoMetadata)
  - Prompt: Generate title_tag (≤60 chars with primary keyword), meta_description (≤160 chars with keyword + CTA), list primary and secondary keywords found
  - Return SeoMetadata serialized as JSON string

File: app/graph/tools/linking_tool.py
- @tool function: linking_tool(outline_json: str, themes_json: str) -> str
  - Use structured_llm = get_llm().with_structured_output(LinkingSuggestions)
  - Prompt: Suggest 3-5 internal links (anchor_text + suggested_target_topic) and 2-4 external links (authoritative source_url + placement context)
  - Return LinkingSuggestions serialized as JSON string

IMPORTANT: Every tool must use with_structured_output() for Pydantic enforcement. No raw llm.invoke() calls. No untyped dict returns.
Do NOT implement nodes, graph assembly, or API routes yet.
```

---

## Prompt 6: SEO Validator Tool (Programmatic, No LLM)

```
Implement the SEO validator tool as a purely programmatic checker — no LLM calls.

File: app/graph/tools/seo_validator.py
- Import QAResult, SeoMetadata, Keyword from app.graph.state
- Import re for regex operations

- @tool function: seo_validator_tool(article: str, metadata_json: str, keywords_json: str, target_word_count: int) -> str
  - Parse metadata_json into SeoMetadata, keywords_json into List[Keyword]
  - Extract primary_keyword (first keyword where is_primary=True, or first keyword)
  
  Implement these 10 checks, each deducting points from a starting score of 100:

  1. PRIMARY_KEYWORD_IN_H1 (-15 if fail):
     - Extract the first markdown H1 (# ...) from article
     - Check if primary_keyword (case-insensitive) is present

  2. PRIMARY_KEYWORD_IN_INTRO (-15 if fail):
     - Take first 500 characters of article (after H1)
     - Check if primary_keyword (case-insensitive) appears

  3. KEYWORD_DENSITY (-10 if fail):
     - Count occurrences of primary_keyword in full article (case-insensitive)
     - Calculate density = (count * len(keyword.split())) / total_words * 100
     - Fail if density < 0.5% or > 3%

  4. H2_KEYWORD_COVERAGE (-10 if fail):
     - Extract all H2 headings (## ...)
     - Check that at least 2 H2s contain the primary keyword OR any secondary keyword
  
  5. WORD_COUNT_TARGET (-10 if fail):
     - Count words in article
     - Fail if outside ±15% of target_word_count

  6. TITLE_TAG_LENGTH (-10 if fail):
     - Fail if metadata.title_tag > 60 chars

  7. META_DESCRIPTION_LENGTH (-10 if fail):
     - Fail if metadata.meta_description > 160 chars

  8. HEADING_HIERARCHY (-10 if fail):
     - Parse all headings (H1, H2, H3)
     - Fail if: no H1, H3 appears before any H2, or multiple H1s exist

  9. NO_KEYWORD_STUFFING (-10 if fail):
     - Fail if keyword_density > 3%

  10. MIN_SECTION_LENGTH (-5 if fail):
      - Split article by H2 headings
      - Fail if any H2 section has fewer than 100 words

  For each failed check: append a descriptive issue string to issues list.
  For each passed check with room for improvement: append a suggestion.
  
  Construct and return QAResult(score=max(0, score), passed=(score >= settings.QA_PASS_SCORE), issues=issues, suggestions=suggestions)
  Serialize as JSON string for return.

File: tests/test_seo_validator.py
- Write 5 tests:
  1. test_perfect_article_scores_high: Create an article that passes all checks, assert score >= 80 and passed=True
  2. test_missing_keyword_in_h1_deducts_points: Article with no keyword in H1, assert "H1" in issues
  3. test_title_tag_too_long: Metadata with 80-char title, assert score deducted
  4. test_word_count_off_target: Article 50% shorter than target, assert issue reported
  5. test_keyword_stuffing_detected: Article with keyword repeated 50 times in 200 words, assert stuffing issue

Do NOT implement nodes or the graph.
```

---

## Prompt 7: Graph Nodes — All 6 Nodes

```
Implement all 6 LangGraph nodes. Each node reads from ArticleGenerationState and returns a partial state update dict.

File: app/graph/nodes/orchestrator.py
- orchestrator_node(state: ArticleGenerationState) -> dict:
  - Validate that state["topic"] is non-empty (raise ValueError if empty)
  - Set word_count to state["word_count"] or default 1500
  - Set language to state["language"] or default "en"
  - Generate job_id as str(uuid4())
  - Return: { job_id, status: "researching", retry_counts: {"research":0, "outline":0, "writer":0, "qa":0}, revision_count: 0, created_at: ISO timestamp, updated_at: ISO timestamp }

File: app/graph/nodes/research.py
- research_node(state: ArticleGenerationState) -> dict:
  - Import and call serp_fetch_tool with state["topic"]
  - Call theme_extractor_tool with the SERP results (serialize as JSON)
  - Parse ThemeAnalysis from the response
  - Return: { serp_results, common_themes, extracted_keywords, competitor_structures, faq_questions, status: "outlining", updated_at }
  - On exception: return { errors: [error msg], retry_counts with research incremented }

File: app/graph/nodes/outline.py
- outline_node(state: ArticleGenerationState) -> dict:
  - Call outline_builder_tool with themes, keywords (serialized), word_count
  - Parse OutlineOutput, extract sections list
  - Return: { outline: sections, status: "writing", updated_at }
  - On exception: return { errors, retry_counts with outline incremented }

File: app/graph/nodes/writer.py
- writer_node(state: ArticleGenerationState) -> dict:
  - If state["qa_result"] exists and not passed: include QA feedback (issues, suggestions) in the writer prompt context so the writer can revise
  - Call article_writer_tool with outline, keywords, themes, language, faq_questions
  - Call metadata_generator_tool with article content and primary keyword
  - Call linking_tool with outline and themes
  - Parse ArticleDraft, SeoMetadata, LinkingSuggestions from responses
  - Return: { article_draft: draft.content, seo_metadata, internal_links, external_references, status: "qa", updated_at }
  - On exception: return { errors, retry_counts with writer incremented }

File: app/graph/nodes/qa.py
- qa_node(state: ArticleGenerationState) -> dict:
  - Call seo_validator_tool with article_draft, seo_metadata (serialized), keywords (serialized), word_count
  - Parse QAResult from response
  - If result.passed: return { qa_result, final_article: state["article_draft"], status: "done", updated_at }
  - If not passed: return { qa_result, revision_count: state["revision_count"] + 1, status: "writing", updated_at }
  - On exception: return { errors }

File: app/graph/nodes/output_builder.py
- output_builder_node(state: ArticleGenerationState) -> dict:
  - This is the final assembly node
  - If final_article is None (QA capped revisions), set final_article = article_draft (best effort)
  - Return: { final_article, status: "done", updated_at }

IMPORTANT: Each node must handle exceptions gracefully and append to errors list. Every node must update the "updated_at" timestamp.
Do NOT implement the graph assembly or API routes.
```

---

## Prompt 8: Graph Assembly — Nodes + Conditional Edges + Checkpointer

```
Assemble the complete LangGraph StateGraph with all nodes, edges, conditional routing, and PostgreSQL checkpointing.

File: app/graph/graph_builder.py

- Import StateGraph, START, END from langgraph.graph
- Import ArticleGenerationState from app.graph.state
- Import all 6 nodes from app.graph.nodes.*
- Import get_checkpointer from app.db.checkpointer
- Import settings from app.config

Implement build_graph(checkpointer=None) -> CompiledGraph:
  1. Create StateGraph(ArticleGenerationState) as builder
  
  2. Add all 6 nodes:
     - "orchestrator" -> orchestrator_node
     - "research" -> research_node
     - "outline" -> outline_node
     - "writer" -> writer_node
     - "qa" -> qa_node
     - "output" -> output_builder_node
     - "error_handler" -> error_handler_node (implement inline: sets status="failed", returns final state)
  
  3. Add edges:
     - START -> "orchestrator"
     - "orchestrator" -> "research"
     - "output" -> END
     - "error_handler" -> END
  
  4. Implement 4 conditional routing functions:
  
     route_after_research(state):
       - If retry_counts["research"] >= settings.MAX_RETRIES: return "error_handler"
       - If serp_results exists and is non-empty: return "outline"  
       - Else: return "research" (retry)
     
     route_after_outline(state):
       - If retry_counts["outline"] >= settings.MAX_RETRIES: return "error_handler"
       - If outline exists and is non-empty: return "writer"
       - Else: return "outline" (retry)
     
     route_after_writer(state):
       - If retry_counts["writer"] >= settings.MAX_RETRIES: return "error_handler"
       - If article_draft exists and is non-empty: return "qa"
       - Else: return "writer" (retry)
     
     route_after_qa(state):
       - If status == "done": return "output"
       - If revision_count >= 3: return "output" (publish best effort)
       - Else: return "writer" (revision cycle)
  
  5. Add conditional edges:
     - builder.add_conditional_edges("research", route_after_research)
     - builder.add_conditional_edges("outline", route_after_outline)
     - builder.add_conditional_edges("writer", route_after_writer)
     - builder.add_conditional_edges("qa", route_after_qa)
  
  6. Compile: graph = builder.compile(checkpointer=checkpointer)
  7. Return graph

Also implement a convenience function:
  get_default_graph() -> CompiledGraph:
    - Gets checkpointer from get_checkpointer(settings.DATABASE_URL)
    - Returns build_graph(checkpointer=checkpointer)

File: tests/test_graph_flow.py
- Write 3 tests:
  1. test_graph_compiles_without_checkpointer: Call build_graph(checkpointer=None), assert it returns a compiled graph
  2. test_graph_has_all_nodes: Check that all 7 node names exist in the graph
  3. test_route_after_qa_done: Create a mock state with status="done", assert route_after_qa returns "output"

Do NOT implement API routes yet.
```

---

## Prompt 9: FastAPI API Layer — Routes, Background Tasks, Job Management

```
Implement the FastAPI application with all API endpoints, background job execution, and proper error handling.

File: app/api/routes.py

Define Pydantic request/response models:
1. CreateJobRequest(BaseModel): topic (str, min_length=3), word_count (int, default=1500, ge=500, le=5000), language (str, default="en")
2. JobStatusResponse(BaseModel): job_id (str), topic (str), status (str), seo_score (Optional[int]), created_at (str), updated_at (str), error_message (Optional[str])
3. ArticleResultResponse(BaseModel): job_id (str), topic (str), article (str), seo_metadata (dict), keywords (list), internal_links (list), external_references (list), seo_score (int), word_count_actual (int)

Implement the router (APIRouter with prefix="/jobs", tags=["jobs"]):

POST / — Create a new generation job
  - Accept CreateJobRequest body
  - Call repository.create_job() to persist job in DB
  - Launch the LangGraph pipeline as a FastAPI BackgroundTask:
    - Initialize state with topic, word_count, language from request
    - Get the compiled graph
    - Use config = {"configurable": {"thread_id": f"seo-job:{job_id}"}}
    - Run: graph.invoke(initial_state, config)
    - On completion: update job status in DB, save article result to DB
    - On failure: update job status to "failed" with error_message
  - Return 202 Accepted with { job_id, status: "pending" }

GET /{job_id} — Get job status
  - Fetch job from repository
  - Return 404 if not found
  - Return JobStatusResponse

GET /{job_id}/result — Get completed article
  - Fetch article from repository
  - Return 404 if not found or job not complete
  - Return ArticleResultResponse

POST /{job_id}/resume — Resume a failed/interrupted job
  - Fetch job from repository
  - Return 404 if not found
  - Launch BackgroundTask that calls graph.invoke(None, config) — None signals resume
  - Update job status to "resuming"
  - Return 202 Accepted

GET / — List all jobs
  - Accept query params: limit (int, default=20), offset (int, default=0)
  - Return list of JobStatusResponse

File: app/main.py
  - Create FastAPI app with title="SEO Article Generation API", version="1.0.0"
  - Include the router from api/routes.py
  - Add a startup event that calls init_db() to create tables
  - Add a health check endpoint: GET /health returning {"status": "healthy"}
  - Add CORS middleware allowing all origins (for development)

Do NOT implement tests for this step — we'll do integration tests last.
```

---

## Prompt 10: Docker Compose, README, Example Output & Integration Test

```
Finalize the project with Docker setup, comprehensive README, a concrete example, and an integration test.

File: docker-compose.yml
  - Service "db": postgres:16-alpine, port 5432:5432, env POSTGRES_USER/PASSWORD/DB matching .env.example, volume pgdata:/var/lib/postgresql/data, healthcheck with pg_isready
  - Service "app": build from Dockerfile, port 8000:8000, depends_on db (condition: service_healthy), env_file: .env, command: uvicorn app.main:app --host 0.0.0.0 --port 8000

File: Dockerfile
  - FROM python:3.12-slim
  - WORKDIR /app
  - COPY requirements.txt and install
  - COPY app/ into /app/app/
  - EXPOSE 8000
  - CMD uvicorn app.main:app --host 0.0.0.0 --port 8000

File: .env.example (update with full list)
  - OPENAI_API_KEY=sk-your-key-here
  - SERPAPI_KEY=your-serpapi-key (optional, will use mock data if missing)
  - DATABASE_URL=postgresql://seo_user:seo_pass@db:5432/seo_agent
  - LLM_MODEL=gpt-4o
  - MAX_RETRIES=3
  - QA_PASS_SCORE=80

File: README.md — Complete documentation:
  ## SEO Article Generation System
  ### Architecture (brief: multi-agent LangGraph with PostgreSQL persistence)
  ### Design Decisions (explain: why LangGraph, why Pydantic-enforced tools, why QA revision loop, why PostgresSaver for durability)
  ### Setup Instructions
    1. Clone repo
    2. Copy .env.example to .env, fill in API keys  
    3. docker-compose up -d
    4. API available at http://localhost:8000
    5. Swagger docs at http://localhost:8000/docs
  ### API Usage
    - Show curl examples for: POST /jobs, GET /jobs/{id}, GET /jobs/{id}/result, POST /jobs/{id}/resume
  ### Example Input → Output
    - Input: { "topic": "best productivity tools for remote teams", "word_count": 1500 }
    - Output: Show a realistic, complete JSON response with: article (first 500 chars + "...truncated"), seo_metadata, keywords list, internal_links (3-5), external_references (2-4), seo_score
  ### Running Tests: pytest tests/ -v
  ### Architecture Diagram: The ASCII diagram from the architecture doc

File: tests/test_graph_flow.py (ADD to existing file, don't overwrite previous tests)
  - Add test_full_pipeline_with_mock_serp:
    - Build graph WITHOUT checkpointer (in-memory)
    - Mock the LLM calls to return predetermined structured outputs
    - Run the full pipeline with topic="best productivity tools for remote teams", word_count=1500, language="en"
    - Assert: final state has status="done", final_article is not None, seo_metadata is not None, internal_links has 3-5 items, external_references has 2-4 items, qa_result.score >= 0

This is the final prompt — after this, the project should be fully functional and ready for submission.
```
