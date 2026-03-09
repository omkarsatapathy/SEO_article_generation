import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=1500)
    language: Mapped[str] = mapped_column(String(10), default="en")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    thread_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    seo_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    articles: Mapped[list["GeneratedArticle"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class GeneratedArticle(Base):
    __tablename__ = "generated_articles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("generation_jobs.job_id"), nullable=False
    )
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_article: Mapped[str | None] = mapped_column(Text, nullable=True)
    seo_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    keywords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    internal_links: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    external_refs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    seo_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count_actual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    job: Mapped["GenerationJob"] = relationship(back_populates="articles")
