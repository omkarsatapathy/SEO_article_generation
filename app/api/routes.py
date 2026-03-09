import asyncio
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repository import JobRepository, get_session_factory
from app.graph.graph_builder import build_graph
from app.graph.state import ArticleGenerationState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Module-level session factory — initialised lazily on first use
_session_factory = None


def _get_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory(settings.DATABASE_URL)
    return _session_factory


async def get_repo() -> JobRepository:
    async with _get_factory()() as session:
        yield JobRepository(session)


# ── Request / Response models ─────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    topic: str = Field(..., min_length=3)
    word_count: int = Field(default=1500, ge=500, le=5000)
    language: str = Field(default="en")


class JobStatusResponse(BaseModel):
    job_id: str
    topic: str
    status: str
    seo_score: Optional[int] = None
    created_at: str
    updated_at: str
    error_message: Optional[str] = None


class ArticleResultResponse(BaseModel):
    job_id: str
    topic: str
    article: str
    seo_metadata: dict
    keywords: list
    internal_links: list
    external_references: list
    seo_score: int
    word_count_actual: int


# ── Background pipeline runner ────────────────────────────────────────────────

async def _run_pipeline(job_id: uuid.UUID, topic: str, word_count: int, language: str) -> None:
    """Execute the LangGraph pipeline and persist results."""
    import time
    start = time.time()
    logger.info("▶▶▶ Pipeline background task STARTED for job %s", job_id)
    logger.info("    Topic: %s | Words: %d | Language: %s", topic, word_count, language)

    factory = _get_factory()
    async with factory() as session:
        repo = JobRepository(session)
        try:
            graph = build_graph(checkpointer=None)
            initial_state: ArticleGenerationState = {
                "job_id": str(job_id),
                "topic": topic,
                "word_count": word_count,
                "language": language,
                "status": "pending",
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
            config = {"configurable": {"thread_id": f"seo-job:{job_id}"}}

            logger.info("    Invoking LangGraph pipeline...")
            # Run the synchronous graph in a thread pool so the asyncio event
            # loop stays free to service SSE log-stream clients while the
            # pipeline executes.
            final_state = await asyncio.to_thread(graph.invoke, initial_state, config)
            elapsed = time.time() - start
            logger.info("    Graph completed in %.1f seconds", elapsed)

            # Persist article result
            seo_score = (
                final_state["qa_result"].score
                if final_state.get("qa_result")
                else None
            )
            keywords = [
                k.model_dump() for k in (final_state.get("extracted_keywords") or [])
            ]
            internal_links = [
                lnk.model_dump() for lnk in (final_state.get("internal_links") or [])
            ]
            external_refs = [
                ref.model_dump() for ref in (final_state.get("external_references") or [])
            ]
            seo_meta = (
                final_state["seo_metadata"].model_dump()
                if final_state.get("seo_metadata")
                else {}
            )
            article_text = final_state.get("final_article") or ""
            word_count_actual = len(article_text.split())

            await repo.save_article(
                job_id=job_id,
                article_data={
                    "topic": topic,
                    "final_article": article_text,
                    "seo_metadata": seo_meta,
                    "keywords": keywords,
                    "internal_links": internal_links,
                    "external_refs": external_refs,
                    "seo_score": seo_score or 0,
                    "word_count_actual": word_count_actual,
                },
            )
            await repo.update_job_status(
                job_id=job_id,
                status="done",
                seo_score=seo_score,
            )
            elapsed = time.time() - start
            logger.info("▶▶▶ Pipeline COMPLETE for job %s — %.1fs total, %d words, score %s",
                         job_id, elapsed, word_count_actual, seo_score)

        except Exception as exc:
            elapsed = time.time() - start
            logger.exception("▶▶▶ Pipeline FAILED for job %s after %.1fs: %s", job_id, elapsed, exc)
            await repo.update_job_status(
                job_id=job_id,
                status="failed",
                error_message=str(exc),
            )


async def _resume_pipeline(job_id: uuid.UUID) -> None:
    """Resume an interrupted pipeline using LangGraph checkpointing."""
    factory = _get_factory()
    async with factory() as session:
        repo = JobRepository(session)
        try:
            graph = build_graph(checkpointer=None)
            config = {"configurable": {"thread_id": f"seo-job:{job_id}"}}
            # Passing None as input signals LangGraph to resume from the last checkpoint
            await asyncio.to_thread(graph.invoke, None, config)
            await repo.update_job_status(job_id=job_id, status="done")
        except Exception as exc:
            logger.exception("Resume failed for job %s: %s", job_id, exc)
            await repo.update_job_status(
                job_id=job_id,
                status="failed",
                error_message=str(exc),
            )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", status_code=202)
async def create_job(
    body: CreateJobRequest,
    background_tasks: BackgroundTasks,
    repo: JobRepository = Depends(get_repo),
):
    """Create a new SEO article generation job."""
    job = await repo.create_job(
        topic=body.topic,
        word_count=body.word_count,
        language=body.language,
    )
    background_tasks.add_task(
        _run_pipeline,
        job_id=job.job_id,
        topic=body.topic,
        word_count=body.word_count,
        language=body.language,
    )
    return {"job_id": str(job.job_id), "status": "pending"}


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: uuid.UUID,
    repo: JobRepository = Depends(get_repo),
):
    """Get the current status of a generation job."""
    job = await repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=str(job.job_id),
        topic=job.topic,
        status=job.status,
        seo_score=job.seo_score,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        error_message=job.error_message,
    )


@router.get("/{job_id}/result", response_model=ArticleResultResponse)
async def get_job_result(
    job_id: uuid.UUID,
    repo: JobRepository = Depends(get_repo),
):
    """Retrieve the completed article and SEO metadata."""
    job = await repo.get_job(job_id)
    if job is None or job.status != "done":
        raise HTTPException(
            status_code=404,
            detail="Article not found or job not yet complete",
        )
    article = await repo.get_article(job_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article record not found")
    return ArticleResultResponse(
        job_id=str(article.job_id),
        topic=article.topic,
        article=article.final_article or "",
        seo_metadata=article.seo_metadata or {},
        keywords=article.keywords or [],
        internal_links=article.internal_links or [],
        external_references=article.external_refs or [],
        seo_score=article.seo_score or 0,
        word_count_actual=article.word_count_actual or 0,
    )


@router.post("/{job_id}/resume", status_code=202)
async def resume_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    repo: JobRepository = Depends(get_repo),
):
    """Resume a failed or interrupted job from its last checkpoint."""
    job = await repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await repo.update_job_status(job_id=job_id, status="resuming")
    background_tasks.add_task(_resume_pipeline, job_id=job_id)
    return {"job_id": str(job_id), "status": "resuming"}


@router.get("/", response_model=List[JobStatusResponse])
async def list_jobs(
    limit: int = 20,
    offset: int = 0,
    repo: JobRepository = Depends(get_repo),
):
    """List all generation jobs with pagination."""
    jobs = await repo.list_jobs(limit=limit, offset=offset)
    return [
        JobStatusResponse(
            job_id=str(j.job_id),
            topic=j.topic,
            status=j.status,
            seo_score=j.seo_score,
            created_at=j.created_at.isoformat(),
            updated_at=j.updated_at.isoformat(),
            error_message=j.error_message,
        )
        for j in jobs
    ]

