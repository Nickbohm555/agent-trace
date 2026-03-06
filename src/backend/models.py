from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TraceRecord(Base):
    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(255), index=True)
    experiment_name: Mapped[str | None] = mapped_column(String(255), index=True)
    environment: Mapped[str | None] = mapped_column(String(120))

    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[float | None] = mapped_column(Float)

    input_payload: Mapped[Any | None] = mapped_column(JSON)
    output_payload: Mapped[Any | None] = mapped_column(JSON)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    trace_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    total_tokens: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)

    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    spans: Mapped[list["TraceSpanRecord"]] = relationship(
        back_populates="trace", cascade="all, delete-orphan"
    )


class TraceSpanRecord(Base):
    __tablename__ = "trace_spans"
    __table_args__ = (
        UniqueConstraint("trace_pk", "span_id", name="uq_trace_spans_trace_pk_span_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_pk: Mapped[int] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"), index=True)

    span_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255), index=True)

    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[float | None] = mapped_column(Float)

    status_message: Mapped[str | None] = mapped_column(String(255))
    input_payload: Mapped[Any | None] = mapped_column(JSON)
    output_payload: Mapped[Any | None] = mapped_column(JSON)
    tool_call: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    error_message: Mapped[str | None] = mapped_column(String(1024))
    error_type: Mapped[str | None] = mapped_column(String(255))
    error_stacktrace: Mapped[str | None] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trace: Mapped[TraceRecord] = relationship(back_populates="spans")
