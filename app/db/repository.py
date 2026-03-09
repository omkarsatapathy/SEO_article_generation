import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, GeneratedArticle, GenerationJob


# ── Engine / session helpers ─────────────────────────────────────────────────

def get_async_engine(db_url: str):
    """
    Return an async SQLAlchemy engine.

    Converts a plain postgresql:// URL to postgresql+asyncpg:// automatically.
    """
    async_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(async_url, echo=False)


def get_session_factory(db_url: str) -> async_sessionmaker[AsyncSession]:
    engine = get_async_engine(db_url)
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(db_url: str) -> None:
    """Create all ORM-managed tables if they do not already exist."""
    engine = get_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Repository ───────────────────────────────────────────────────────────────

class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_job(
        self, topic: str, word_count: int, language: str
    ) -> GenerationJob:
        job_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        job = GenerationJob(
            job_id=job_id,
            topic=topic,
            word_count=word_count,
            language=language,
            status="pending",
            thread_id=f"seo-job:{job_id}",
            created_at=now,
            updated_at=now,
        )
        self._session.add(job)
        await self._session.commit()
        await self._session.refresh(job)
        return job

    async def get_job(self, job_id: uuid.UUID) -> Optional[GenerationJob]:
        result = await self._session.execute(
            select(GenerationJob).where(GenerationJob.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def update_job_status(
        self,
        job_id: uuid.UUID,
        status: str,
        seo_score: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        job = await self.get_job(job_id)
        if job is None:
            return
        job.status = status
        job.updated_at = datetime.now(timezone.utc)
        if seo_score is not None:
            job.seo_score = seo_score
        if error_message is not None:
            job.error_message = error_message
        await self._session.commit()

    async def save_article(
        self, job_id: uuid.UUID, article_data: dict
    ) -> GeneratedArticle:
        now = datetime.now(timezone.utc)
        article = GeneratedArticle(
            id=uuid.uuid4(),
            job_id=job_id,
            topic=article_data.get("topic"),
            final_article=article_data.get("final_article"),
            seo_metadata=article_data.get("seo_metadata"),
            keywords=article_data.get("keywords"),
            internal_links=article_data.get("internal_links"),
            external_refs=article_data.get("external_refs"),
            seo_score=article_data.get("seo_score"),
            word_count_actual=article_data.get("word_count_actual"),
            created_at=now,
        )
        self._session.add(article)
        await self._session.commit()
        await self._session.refresh(article)
        return article

    async def get_article(
        self, job_id: uuid.UUID
    ) -> Optional[GeneratedArticle]:
        result = await self._session.execute(
            select(GeneratedArticle).where(GeneratedArticle.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_jobs(
        self, limit: int = 20, offset: int = 0
    ) -> List[GenerationJob]:
        result = await self._session.execute(
            select(GenerationJob)
            .order_by(GenerationJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
