# SEO Article Generation System

> **A production-ready, multi-agent LangGraph pipeline for generating SEO-optimized articles with real-time monitoring, crash recovery, and comprehensive quality assurance.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-modern-green?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Framework-purple?logo=langchain)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

---

## 📋 Table of Contents

- [Project Overview](#project-overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Local Setup Guide](#local-setup-guide)
  - [Option 1: Docker Compose (Recommended)](#option-1-docker-compose-recommended)
  - [Option 2: Local Python Environment](#option-2-local-python-environment)
  - [Option 3: Using UV Package Manager](#option-3-using-uv-package-manager)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Development & Testing](#development--testing)
- [Troubleshooting](#troubleshooting)
- [Architecture Deep Dive](#architecture-deep-dive)
- [Contributing](#contributing)

---

## 🎯 Project Overview

The **SEO Article Generation System** is a sophisticated, production-ready application that automatically generates high-quality, SEO-optimized articles through a multi-agent AI pipeline. It combines real-time research (via SerpAPI), intelligent content generation (via Claude/GPT-4), comprehensive quality assurance, and crash-recovery capabilities.

### What It Does

1. **Accepts user input**: Topic, desired word count, and language
2. **Conducts research**: Fetches real SERP data, competitor structures, and FAQs
3. **Generates outlines**: Creates SEO-aligned article structures
4. **Writes content**: Generates sections with internal/external linking
5. **Validates quality**: Runs comprehensive SEO checks with penalty/bonus scoring
6. **Ensures compliance**: Revises content until SEO score ≥ 80 or max revisions reached
7. **Returns results**: Final article with metadata, keywords, links, and SEO score

### Why This Project?

- **Enterprise-grade**: Production-ready code with error handling, async patterns, and proper logging
- **Observable**: Real-time log streaming via Server-Sent Events (SSE) as pipeline runs
- **Resilient**: LangGraph PostgreSQL checkpointing enables crash recovery and resume
- **Modular**: Each agent runs independently with separate retry budgets
- **Configurable**: All tunable parameters (thresholds, prompts, limits) in YAML files
- **Scalable**: Async FastAPI, connection pooling, and stateless design

---

## ✨ Key Features

### Core Capabilities
- 🤖 **Multi-Agent Pipeline**: 7 specialized agents (orchestrator, research, outline, writer, QA, output builder, error handler)
- 📊 **Real-time Monitoring**: SSE log streaming with ring-buffer (last 400 log entries)
- 💾 **Crash Recovery**: PostgreSQL checkpoint storage for resuming interrupted pipelines
- 🔄 **Retry Logic**: Independent per-node retry budgets (max 3 retries per agent)
- 🧪 **Quality Assurance**: QA agent with 15+ semantic checks and penalty/bonus scoring
- 🔗 **Smart Linking**: Automatic internal link placement and external reference deduplication

### API Features
- ✅ **Job Management**: Create, track, and resume article generation jobs
- 📡 **Async Operations**: Non-blocking background processing with 202 Accepted responses
- 🌐 **CORS Support**: Built-in cross-origin resource sharing
- 📝 **Health Checks**: Liveness probe endpoint for load balancers
- 🔍 **Result Retrieval**: Fetch complete articles with all metadata

### Operational Features
- 🐳 **Docker Support**: Docker Compose for local development and production
- ⚙️ **Configuration System**: YAML-based hyperparameters, prompts, and settings
- 🧬 **Pydantic Models**: Strong type validation for all inputs/outputs
- 🗃️ **SQLAlchemy ORM**: Async database access with migrations support
- 🔐 **Environment Variables**: Secrets management via .env files

---

## 🏗️ System Architecture

The system uses a **LangGraph state machine** with conditional routing, retry logic, and persistent checkpointing:

```
INPUT (topic, word_count, language)
         ↓
    [ORCHESTRATOR] ← Validate input, initialize job
         ↓
    [RESEARCH] ← Fetch SERP results, extract themes/FAQs (max 3 retries)
         ↓
    [OUTLINE] ← Generate article structure with keyword mapping (max 3 retries)
         ↓
    [WRITER] ← Generate sections, link placement, metadata (max 3 retries)
         ↓
    [QA] ← Validate SEO score, check 15+ quality metrics
         ├─→ Score ≥ 80? → [OUTPUT BUILDER]
         ├─→ Score < 80 & revisions < 3? → [WRITER] (revision loop)
         └─→ Max revisions reached? → [OUTPUT BUILDER] (best-effort)
         ↓
   [OUTPUT BUILDER] ← Assemble final article + references
         ↓
OUTPUT (final_article, seo_metadata, keywords, links, score)
```

### Data Flow

- **State Management**: All data flows through `ArticleGenerationState` (single source of truth)
- **Retry Logic**: Each node has independent `retry_counts` tracking
- **Error Handling**: Append-only error list prevents data loss
- **Checkpointing**: LangGraph PostgresSaver snapshots state after each node (resumable)
- **Database Persistence**: SQLAlchemy ORM stores jobs and articles; separate checkpoint tables

### LangGraph Node Types

| Node | Type | Role | Tools |
|------|------|------|-------|
| **ORCHESTRATOR** | ReAct Agent | Input validation, job initialization | `validate_input_tool`, `job_init_tool` |
| **RESEARCH** | ReAct Agent | SERP data collection, theme extraction | `serp_fetch_tool`, `theme_extractor_tool`, `faq_extractor_tool` |
| **OUTLINE** | ReAct Agent | Article structure generation | `outline_builder_tool`, `keyword_mapper_tool` |
| **WRITER** | Sequential | Direct tool calls (deterministic) | `article_writer_tool`, `linking_tool`, `metadata_generator_tool` |
| **QA** | ReAct Agent | SEO scoring and validation | `seo_validator_tool`, `score_calculator_tool` |
| **OUTPUT_BUILDER** | Plain Function | Final assembly + reference merging | (no tools) |
| **ERROR_HANDLER** | Plain Function | Terminal error state | (no tools) |

**→ For detailed architecture diagrams and design decisions, see [docs/SEO_Agent_Architecture.md](docs/SEO_Agent_Architecture.md)**

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Agent Framework** | LangGraph | Stateful graph orchestration, conditional routing, checkpointing |
| **LLM** | Claude 3.5 Sonnet / GPT-4o | Article generation, QA, theme extraction |
| **API** | FastAPI | Async REST endpoints, CORS, SSE streaming |
| **Web Server** | Uvicorn | ASGI server for FastAPI |
| **Database** | PostgreSQL 16 | Job tracking, article storage, checkpoint persistence |
| **ORM** | SQLAlchemy 2.0 | Async database access with migrations |
| **Validation** | Pydantic v2 | Input/output validation, state models |
| **Checkpointing** | LangGraph PostgresSaver | Crash recovery and pipeline resumption |
| **Search Data** | SerpAPI | Real search results and competitor analysis |
| **Async HTTP** | HTTPX | Non-blocking HTTP requests |
| **Configuration** | YAML + dataclasses | Decoupled hyperparameters and prompts |
| **Containerization** | Docker + Compose | Reproducible environments |
| **Testing** | Pytest + Pytest-asyncio | Unit and integration tests |

---

## 📦 Prerequisites

Before setting up locally, ensure you have:

### Required

- **Python 3.11+** (3.12 recommended)
- **PostgreSQL 14+** (or Docker for containerized setup)
- **API Keys**:
  - `OPENAI_API_KEY` (for Claude/GPT-4 LLM access)
  - `SERPAPI_KEY` (for search results API)

### Optional

- **Docker & Docker Compose** (for containerized setup)
- **UV** (fast Python package manager, optional but recommended)
- **Git** (for version control)

### Verify Installation

```bash
# Python version
python3 --version          # Should be 3.11+

# PostgreSQL (if installing locally)
psql --version             # Should be 14+

# Docker (if using containerized setup)
docker --version
docker-compose --version
```

---

## 🚀 Local Setup Guide

Choose **one** of the three setup methods below:

### Option 1: Docker Compose (Recommended)

This is the **easiest and most reliable** approach for local development. It automatically sets up PostgreSQL, applies migrations, and runs the API.

#### Steps

1. **Clone the repository** (if you haven't already)

```bash
cd /path/to/SEO_article_generation
```

2. **Create a `.env` file** with your API keys:

```bash
cat > .env << 'EOF'
# .env — API keys and database connection
OPENAI_API_KEY=sk-proj-your-openai-key-here
SERPAPI_KEY=your-serpapi-key-here
DATABASE_URL=postgresql://seo_user:seo_pass@db:5432/seo_agent

# Optional: Override defaults from settings.yaml
LLM_MODEL=gpt-4o
WRITER_LLM_MODEL=gpt-4o
QA_PASS_SCORE=80
EOF
```

3. **Start the application stack**:

```bash
docker-compose up -d
```

This will:
- Start PostgreSQL at `localhost:5432`
- Build the FastAPI application image
- Initialize databases and run migrations
- Start the API at `http://localhost:8000`

4. **Verify the setup**:

```bash
# Check if services are healthy
docker-compose ps

# View API logs
docker-compose logs -f app

# Test the API
curl http://localhost:8000/health
```

5. **Stop the services**:

```bash
docker-compose down

# To also remove volumes (clean slate on next startup)
docker-compose down -v
```

#### Access Points

- **API**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8000/redoc (ReDoc)
- **PostgreSQL**: `postgresql://seo_user:seo_pass@localhost:5432/seo_agent`

**Advantages:**
- ✅ No local PostgreSQL installation required
- ✅ Isolated container environment
- ✅ Reproducible across machines
- ✅ Easy to tear down and start fresh

---

### Option 2: Local Python Environment

For development with direct Python execution and local debugging.

#### Steps

1. **Install PostgreSQL locally** (macOS):

```bash
# Using Homebrew
brew install postgresql@16

# Start the service
brew services start postgresql@16

# Verify
psql --version
```

Or **on Ubuntu/Debian**:

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib

# Verify
psql --version
```

2. **Create the database and user**:

```bash
# Login to PostgreSQL
psql -U postgres

# Inside psql:
CREATE USER seo_user WITH PASSWORD 'seo_pass';
CREATE DATABASE seo_agent OWNER seo_user;
GRANT ALL PRIVILEGES ON DATABASE seo_agent TO seo_user;
\q
```

3. **Clone the repository and navigate to it**:

```bash
cd /path/to/SEO_article_generation
```

4. **Create a Python virtual environment**:

```bash
# Create venv
python3.12 -m venv venv

# Activate venv
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate
```

5. **Install dependencies**:

```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Or use `pyproject.toml` with pip:

```bash
pip install -e .
```

6. **Create a `.env` file**:

```bash
cat > .env << 'EOF'
OPENAI_API_KEY=sk-proj-your-openai-key-here
SERPAPI_KEY=your-serpapi-key-here
DATABASE_URL=postgresql://seo_user:seo_pass@localhost:5432/seo_agent
EOF
```

7. **Initialize the database** (run migrations):

```bash
# If you have Alembic set up:
alembic upgrade head

# Or manually create tables (ensure they're defined in app/db/models.py):
python3 -c "
from app.db.models import Base
from sqlalchemy import create_engine
engine = create_engine('postgresql://seo_user:seo_pass@localhost:5432/seo_agent')
Base.metadata.create_all(engine)
print('✅ Tables created successfully')
"
```

8. **Start the development server**:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or use the launch script:

```bash
chmod +x launch.sh
./launch.sh
```

#### Access Points

- **API**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **PostgreSQL**: `postgresql://seo_user:seo_pass@localhost:5432/seo_agent`

**Advantages:**
- ✅ Direct debugging with IDE breakpoints
- ✅ Faster iteration during development
- ✅ Full control over environment

**Disadvantages:**
- ❌ Requires local PostgreSQL setup
- ❌ More manual configuration

---

### Option 3: Using UV Package Manager

For fast, deterministic dependency installation with the `uv` package manager.

#### Prerequisites

Install `uv`:

```bash
# macOS
brew install uv

# Or from https://docs.astral.sh/uv/getting-started/
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### Steps

1. **Use the provided launch script** (automated):

```bash
chmod +x launch.sh
./launch.sh
```

This will:
- Check for `.env` file (copies `.env.example` if missing)
- Create or activate a UV-managed Python environment
- Install dependencies
- Initialize the database
- Start the server

2. **Or manually set up with UV**:

```bash
# Create environment
uv venv .venv

# Activate
source .venv/bin/activate

# Install dependencies from pyproject.toml
uv pip install -e .

# Run migrations and start server
uvicorn app.main:app --reload
```

**Advantages:**
- ✅ Blazingly fast dependency resolution
- ✅ Reproducible, locked dependency versions
- ✅ Simpler than poetry/pipenv

---

## ⚙️ Configuration

All configuration is managed through **YAML files** in `config/` and **environment variables** in `.env`:

### 1. YAML Configuration Files

Located in `config/`:

#### `hyperparams.yaml` — Numerical Thresholds

```yaml
pipeline:
  max_retries: 3           # Retries per node before error
  max_revisions: 3         # QA → Writer revision cycles

article:
  word_count_default: 1500
  word_count_min: 500
  word_count_max: 5000

qa:
  pass_score: 80           # Minimum SEO score to pass QA
  thresholds:
    keyword_density_min: 0.5%
    keyword_density_max: 3.0%
```

#### `settings.yaml` — Application Settings

```yaml
app:
  title: "SEO Article Generation API"
  version: "1.0.0"
  port: 8000

llm:
  model: "gpt-4o"
  writer_model: "gpt-4-turbo"
  temperature: 0.7

cors:
  allow_origins: ["*"]
```

#### `prompts.yaml` — Agent System Prompts

```yaml
agents:
  research: |
    You are a research specialist...
  writer: |
    You are a professional writer...
  qa: |
    You are a QA expert...
```

### 2. Environment Variables (.env)

**Required:**

```bash
# LLM API Keys
OPENAI_API_KEY=sk-proj-...
SERPAPI_KEY=your-key

# Database connection
DATABASE_URL=postgresql://user:pass@localhost:5432/seo_agent
```

**Optional (overrides YAML defaults):**

```bash
LLM_MODEL=gpt-4o
WRITER_LLM_MODEL=gpt-4-turbo
MAX_RETRIES=3
QA_PASS_SCORE=80
```

### 3. Accessing Configuration in Code

```python
from config.config import cfg

# Access any nested setting
cfg.hyperparams.pipeline.max_retries          # 3
cfg.hyperparams.qa.pass_score                 # 80
cfg.settings.app.title                        # "SEO Article Generation API"
cfg.prompts.agents.research                   # System prompt string

# Settings with env var overrides
from app.config import settings
settings.OPENAI_API_KEY                       # From .env
settings.LLM_MODEL                            # From .env or YAML default
```

---

## ▶️ Running the Application

### Start the Server

```bash
# Using Docker Compose (recommended)
docker-compose up -d

# Or using local Python environment
source venv/bin/activate        # Activate venv if not already
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or using the launch script
./launch.sh
```

### Verify Health

```bash
curl http://localhost:8000/health

# Response:
# {"status": "healthy"}
```

### View API Documentation

Open your browser to:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Check PostgreSQL Connection

```bash
# If using Docker Compose
docker-compose exec db psql -U seo_user -d seo_agent -c "\dt"

# If local PostgreSQL
psql -U seo_user -d seo_agent -c "\dt"
```

---

## 📡 API Documentation

### Base URL

```
http://localhost:8000
```

### Main Endpoints

#### 1. Create Article Generation Job

```http
POST /jobs/
Content-Type: application/json

{
  "topic": "Best AI Tools for 2024",
  "word_count": 2000,
  "language": "en"
}

# Response (202 Accepted):
{
  "job_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "status": "pending",
  "created_at": "2024-03-09T10:30:00Z"
}
```

#### 2. Check Job Status

```http
GET /jobs/{job_id}

# Response:
{
  "job_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "status": "running",
  "seo_score": null,
  "current_node": "research",
  "errors": [],
  "created_at": "2024-03-09T10:30:00Z",
  "updated_at": "2024-03-09T10:31:15Z"
}
```

#### 3. Get Article Result

```http
GET /jobs/{job_id}/result

# Response (when status = "done"):
{
  "job_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "article": "# Best AI Tools for 2024\n\n[content...]",
  "seo_metadata": {
    "title_tag": "Best AI Tools 2024 | Top Solutions Guide",
    "meta_description": "Explore 2024's top AI tools...",
    "h1": "Best AI Tools for 2024",
    "word_count": 2000,
    "keyword_density": 1.2
  },
  "keywords": ["AI tools", "machine learning", ...],
  "internal_links": [["AI Guide", "/guides/ai"]],
  "external_references": [
    {"title": "OpenAI", "url": "https://openai.com", "domain": "openai.com"}
  ],
  "seo_score": 92,
  "word_count_actual": 2018
}
```

#### 4. Resume Interrupted Job

```http
POST /jobs/{job_id}/resume

# Response:
{
  "message": "Job resumed from checkpoint",
  "job_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef"
}
```

#### 5. Stream Real-time Logs

```http
GET /logs/stream
Accept: text/event-stream

# Response (Server-Sent Events):
data: {"level": "INFO", "name": "app.graph.nodes.research", "text": "Fetching SERP results..."}
data: {"level": "INFO", "name": "app.graph.nodes.outline", "text": "Generated outline with 5 sections"}
```

#### 6. Health Check

```http
GET /health

# Response:
{"status": "healthy"}
```

### Request/Response Schemas

See the interactive documentation at http://localhost:8000/docs for complete schemas with examples.

---

## 📁 Project Structure

```
SEO_article_generation/
│
├── 📄 README.md                         # This file
├── 📄 Dockerfile                         # Docker image definition
├── 📄 docker-compose.yml                 # Multi-container orchestration
├── 📄 launch.sh                          # Automated setup script
├── 📄 requirements.txt                   # Pip dependencies
├── 📄 pyproject.toml                     # Project metadata + dependencies
├── 📄 frameworks.toml                    # Framework configuration
│
├── 📂 app/                               # Main application package
│   ├── __init__.py
│   ├── main.py                          # FastAPI app, CORS, lifespan
│   ├── config.py                        # Environment variable settings
│   │
│   ├── 📂 api/                          # REST API layer
│   │   ├── __init__.py
│   │   ├── routes.py                    # Endpoints: /jobs/*, /health
│   │   └── log_stream.py                # SSE endpoint: /logs/stream
│   │
│   ├── 📂 graph/                        # LangGraph agent pipeline
│   │   ├── __init__.py
│   │   ├── state.py                     # ArticleGenerationState model
│   │   ├── graph_builder.py             # build_graph() + routing logic
│   │   │
│   │   ├── 📂 nodes/                    # Agent implementations
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py          # Input validation, job init
│   │   │   ├── research.py              # SERP fetch, theme extraction
│   │   │   ├── outline.py               # Article structure generation
│   │   │   ├── writer.py                # Content generation
│   │   │   ├── qa.py                    # SEO validation & scoring
│   │   │   ├── output_builder.py        # Final assembly
│   │   │   └── error_handler.py         # Error terminal state
│   │   │
│   │   └── 📂 tools/                    # Agent tools
│   │       ├── __init__.py
│   │       ├── serp_fetch.py            # SerpAPI integration
│   │       ├── theme_extractor.py       # Content analysis
│   │       ├── outline_builder.py       # Structure generation
│   │       ├── article_writer.py        # Section writing
│   │       ├── linking_tool.py          # Link placement
│   │       ├── metadata_generator.py    # SEO metadata
│   │       ├── seo_validator.py         # Quality checks
│   │       └── keyword_mapper.py        # Keyword analysis
│   │
│   └── 📂 db/                           # Database layer
│       ├── __init__.py
│       ├── models.py                    # SQLAlchemy ORM models
│       ├── repository.py                # Async CRUD operations
│       └── checkpointer.py              # LangGraph PostgresSaver setup
│
├── 📂 config/                           # Configuration files
│   ├── __init__.py
│   ├── config.py                        # YAML loader
│   ├── hyperparams.yaml                 # Numerical thresholds
│   ├── settings.yaml                    # App settings
│   └── prompts.yaml                     # Agent system prompts
│
├── 📂 tests/                            # Test suite
│   ├── __init__.py
│   ├── conftest.py                      # Pytest fixtures
│   ├── test_serp.py                     # SERP fetch tests
│   ├── test_outline.py                  # Outline generation tests
│   ├── test_seo_validator.py            # QA validator tests
│   ├── test_coerce_links.py             # Link placement tests
│   └── test_graph_flow.py               # End-to-end graph tests
│
├── 📂 docs/                             # Documentation
│   ├── SEO_Agent_Architecture.md        # Detailed architecture
│   └── architecture_diagram.html        # Visual diagram
│
├── 📂 GUI/                              # Frontend
│   └── index.html                       # Simple web UI
│
└── 📂 __pycache__/                      # Python cache (auto-generated)
```

### Key Directories Explained

| Directory | Purpose |
|-----------|---------|
| `app/` | Main application code (API, agents, database) |
| `app/graph/nodes/` | 7 agent implementations |
| `app/graph/tools/` | Tool implementations (SERP fetch, validation, etc.) |
| `app/db/` | SQLAlchemy ORM and LangGraph checkpointing |
| `config/` | External configuration (YAML files) |
| `tests/` | Unit and integration tests |
| `docs/` | Architecture documentation |

---

## 🧪 Development & Testing

### Running Tests

```bash
# Activate virtual environment (if using local setup)
source venv/bin/activate

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_seo_validator.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run async tests only
pytest tests/ -k "async" -v

# Run with live output
pytest tests/ -v -s
```

### Test Files

| File | Coverage |
|------|----------|
| `test_serp.py` | SerpAPI integration and fallback |
| `test_outline.py` | Article structure generation |
| `test_seo_validator.py` | QA scoring and penalties |
| `test_coerce_links.py` | Internal link placement |
| `test_graph_flow.py` | End-to-end pipeline execution |

### Writing New Tests

Example test structure:

```python
import pytest
from app.db.models import GenerationJob

@pytest.mark.asyncio
async def test_job_creation(db_session):
    """Test creating a new generation job."""
    job = GenerationJob(
        topic="Test Topic",
        word_count=1500,
        language="en"
    )
    db_session.add(job)
    await db_session.commit()
    
    assert job.job_id is not None
    assert job.status == "pending"
```

### Debugging

**Enable verbose logging:**

```bash
# Set log level to DEBUG in .env or settings.yaml
LOGGING_LEVEL=DEBUG

# Then run the server
uvicorn app.main:app --reload
```

**Check database state during execution:**

```bash
# In another terminal, connect to PostgreSQL
psql -U seo_user -d seo_agent

# View job status
SELECT job_id, status, seo_score, created_at FROM generation_jobs ORDER BY created_at DESC LIMIT 5;

# View checkpoint progress
SELECT thread_id, checkpoint_ns FROM checkpoints LIMIT 5;
```

---

## 🔧 Troubleshooting

### Common Issues & Solutions

#### 1. **PostgreSQL Connection Error**

```
Error: could not connect to server: Connection refused
```

**Solution:**
- Ensure PostgreSQL is running: `brew services list` (macOS) or `sudo systemctl status postgresql` (Linux)
- If using Docker Compose, ensure db service is healthy: `docker-compose ps`
- Check DATABASE_URL in `.env` matches your setup
- For Docker Compose: `docker-compose logs db`

#### 2. **"OPENAI_API_KEY not provided"**

```
Error: OpenAI API key not set
```

**Solution:**
- Create `.env` file with `OPENAI_API_KEY=sk-proj-...`
- Use `source venv/bin/activate` to load environment
- Verify key is valid at https://platform.openai.com/account/api-keys

#### 3. **Port 8000 Already in Use**

```
Error: Address already in use
```

**Solution:**
```bash
# Kill process using port 8000
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Or use different port
uvicorn app.main:app --port 8001
```

#### 4. **Database Migration Errors**

```
Error: Table generation_jobs does not exist
```

**Solution:**
```bash
# Manually create tables
python3 -c "
from app.db.models import Base
from sqlalchemy import create_engine
url = 'postgresql://seo_user:seo_pass@localhost:5432/seo_agent'
Base.metadata.create_all(create_engine(url))
print('✅ Tables created')
"

# Or use Alembic (if configured)
alembic upgrade head
```

#### 5. **"No module named 'app'" or Import Errors**

**Solution:**
```bash
# Reinstall package in development mode
pip install -e .

# Or add project root to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/path/to/SEO_article_generation"
```

#### 6. **Docker Compose Fails to Build**

```
Error: failed to solve with frontend dockerfile.v0
```

**Solution:**
```bash
# Clean up old images and volumes
docker-compose down -v

# Rebuild from scratch
docker-compose up --build

# Or view build logs
docker-compose logs app
```

#### 7. **SSE Log Stream Not Connecting**

```
Error connecting to /logs/stream endpoint
```

**Solution:**
- Check browser console for errors
- Ensure server is running: `curl http://localhost:8000/health`
- Verify CORS settings in `config/settings.yaml`
- Check server logs: `docker-compose logs -f app`

### Debug Flags & Environment Variables

```bash
# Enable debug logging
export LOGGING_LEVEL=DEBUG

# Disable SSL verification (development only!)
export OPENAI_SKIP_SSL=true

# Use mock SerpAPI responses (for offline testing)
export SERPAPI_MOCK=true

# Single-threaded execution (for debugging)
export LANGCHAIN_VERBOSE=true
```

---

## 📚 Architecture Deep Dive

For comprehensive understanding of the system architecture, refer to:

- **[docs/SEO_Agent_Architecture.md](docs/SEO_Agent_Architecture.md)** — Complete technical specification including:
  - System overview and data flow
  - Node catalogue with tools and iteration limits
  - Conditional routing logic decision tables
  - PostgreSQL two-layer architecture
  - API layer specification
  - Real-time log streaming (SSE) implementation
  - QA scoring system with penalty catalogue
  - Configuration system walkthrough
  - Key design principles
  - Tech stack rationale

### Key Architectural Decisions

1. **State as Single Source of Truth**: All communication via `ArticleGenerationState` (no side channels)
2. **Append-only Error Tracking**: `Annotated[List[str], operator.add]` prevents error loss
3. **Node Independence**: Each node has its own retry budget (`retry_counts` dict)
4. **Sequential Writer**: Direct tool calls instead of ReAct loop for determinism
5. **QA Revision Loop**: Hard ceiling of 3 revisions prevents infinite loops
6. **Pydantic Safety Nets**: Auto-truncation and range-clamping prevent LLM-induced crashes
7. **SSE + asyncio.to_thread**: Non-blocking monitoring while graph runs
8. **Dual DB Layers**: SQLAlchemy for ORM, LangGraph PostgresSaver for checkpoints

---

## 🤝 Contributing

### Development Workflow

1. **Create a feature branch**:
```bash
git checkout -b feature/my-feature
```

2. **Make changes** and write tests:
```bash
# Edit code
vim app/graph/nodes/research.py

# Write tests
vim tests/test_research.py

# Run tests locally
pytest tests/test_research.py -v
```

3. **Commit with clear messages**:
```bash
git commit -m "feat: add support for multi-language research"
```

4. **Push and create pull request**:
```bash
git push origin feature/my-feature
```

### Code Style

- Follow PEP 8 with line length of 100 characters
- Use type hints for all function signatures
- Write docstrings for public functions/classes
- Keep functions under 50 lines where possible

Example:

```python
def my_function(topic: str, word_count: int = 1500) -> ArticleGenerationState:
    """
    Generate an article from a topic.
    
    Args:
        topic: The article topic string
        word_count: Target word count (default: 1500)
    
    Returns:
        ArticleGenerationState with final article content
    
    Raises:
        ValueError: If word_count outside valid range
    """
    if not 500 <= word_count <= 5000:
        raise ValueError(f"Invalid word_count: {word_count}")
    
    # Implementation...
    return state
```

### Areas for Contribution

- **New Agent Nodes**: Add specialized agents for different content types
- **Tool Enhancements**: Improve SERP fetch, linking, or validation
- **LLM Provider Support**: Add Anthropic Claude, Google Gemini variants
- **GUI**: Enhance the browser UI in `GUI/index.html`
- **Testing**: Add more comprehensive test coverage
- **Documentation**: Improve guides and API docs
- **Performance**: Optimize agent loops and database queries

---

## 📖 Additional Resources

### Documentation

- [SEO Agent Architecture](docs/SEO_Agent_Architecture.md) — Detailed technical design
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/) — Agent framework
- [FastAPI Guide](https://fastapi.tiangolo.com/) — API development
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/) — Database layer

### External APIs

- [SerpAPI Docs](https://serpapi.com/docs) — Search results
- [OpenAI API](https://platform.openai.com/docs) — LLM calls
- [Anthropic Claude](https://docs.anthropic.com/) — Alternative LLM

### Community

- Report bugs or suggest features via GitHub Issues
- Discussions and Q&A in GitHub Discussions
- Pull requests welcome!

---

## 📝 License

[Add License Info Here - e.g., MIT, Apache 2.0]

---

## ✍️ Authors & Acknowledgments

- **Project Lead**: Omkar Satapathy
- **Tech Stack**: Built with LangGraph, FastAPI, and PostgreSQL
- **Thanks to**: OpenAI/Anthropic for LLMs, LangChain team for frameworks

---

**Last Updated**: March 2026  
