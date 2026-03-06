"""add trace storage tables

Revision ID: 20260306_01
Revises:
Create Date: 2026-03-06 12:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260306_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trace_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=True),
        sa.Column("experiment_name", sa.String(length=255), nullable=True),
        sa.Column("environment", sa.String(length=120), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("tool_calls", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("errors", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("trace_id", name="uq_traces_trace_id"),
    )
    op.create_index("ix_traces_trace_id", "traces", ["trace_id"], unique=True)
    op.create_index("ix_traces_run_id", "traces", ["run_id"])
    op.create_index("ix_traces_experiment_name", "traces", ["experiment_name"])

    op.create_table(
        "trace_spans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trace_pk", sa.Integer(), sa.ForeignKey("traces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("span_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("status_message", sa.String(length=255), nullable=True),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("tool_call", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("error_stacktrace", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("trace_pk", "span_id", name="uq_trace_spans_trace_pk_span_id"),
    )
    op.create_index("ix_trace_spans_trace_pk", "trace_spans", ["trace_pk"])
    op.create_index("ix_trace_spans_name", "trace_spans", ["name"])


def downgrade() -> None:
    op.drop_index("ix_trace_spans_name", table_name="trace_spans")
    op.drop_index("ix_trace_spans_trace_pk", table_name="trace_spans")
    op.drop_table("trace_spans")

    op.drop_index("ix_traces_experiment_name", table_name="traces")
    op.drop_index("ix_traces_run_id", table_name="traces")
    op.drop_index("ix_traces_trace_id", table_name="traces")
    op.drop_table("traces")
