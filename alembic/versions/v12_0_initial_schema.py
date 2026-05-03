"""MAC_ASD v12.0 — Initial schema (all 16 tables).

Revision ID: v12_0_initial
Revises: None
Create Date: 2026-04-27

Includes:
  - projects, documents, document_chunks (core)
  - audit_logs (Hermes training)
  - domain_traps (BLS — Contractor Trap Library)
  - vendors, materials_catalog, price_lists, price_list_items (procurement)
  - lab_organizations, lab_requests, lab_samples, lab_contracts, lab_acts, lab_reports, lab_control_plans (lab control)
  - lessons_learned (Опытный контур — Lessons Learned)

PostgreSQL extensions: vector, pg_trgm
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "v12_0_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── Core ──
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("status", sa.String(50), default="active"),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id")),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(512)),
        sa.Column("doc_type", sa.String(50)),
        sa.Column("metadata_json", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id")),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("page_number", sa.Integer),
    )

    # ── Audit ──
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("agent_name", sa.String(50)),
        sa.Column("action", sa.String(100)),
        sa.Column("input_data", sa.JSON),
        sa.Column("output_data", sa.JSON),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("timestamp", sa.DateTime, server_default=sa.func.now()),
        sa.Column("is_learned", sa.Boolean, default=False),
    )

    # ── BLS (Legal Traps) ──
    op.create_table(
        "domain_traps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("source", sa.String(255)),
        sa.Column("channel", sa.String(255)),
        sa.Column("category", sa.String(100)),
        sa.Column("weight", sa.Integer, default=100),
        sa.Column("court_cases", sa.JSON),
        sa.Column("mitigation", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("embedding", Vector(1024)),
    )

    # ── Procurement ──
    op.create_table(
        "vendors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_info", sa.JSON),
        sa.Column("rating", sa.Integer, default=5),
        sa.Column("category", sa.String(100)),
        sa.Column("inn", sa.String(12), unique=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "materials_catalog",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("unit", sa.String(20)),
        sa.Column("avg_price", sa.Integer),
        sa.Column("embedding", Vector(1024)),
    )
    # Trigram index on materials_catalog.name
    op.execute(
        "CREATE INDEX ix_material_name_trgm ON materials_catalog "
        "USING gin (name gin_trgm_ops)"
    )

    op.create_table(
        "price_lists",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("vendor_id", sa.Integer, sa.ForeignKey("vendors.id")),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id")),
        sa.Column("valid_until", sa.DateTime),
        sa.Column("currency", sa.String(3), default="RUB"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "price_list_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("price_list_id", sa.Integer, sa.ForeignKey("price_lists.id")),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("materials_catalog.id")),
        sa.Column("price_value", sa.Integer, nullable=False),
        sa.Column("quantity_available", sa.Integer),
    )

    # ── Lab Control ──
    op.create_table(
        "lab_organizations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("inn", sa.String(12), unique=True),
        sa.Column("accreditation_number", sa.String(50)),
        sa.Column("accreditation_date", sa.DateTime),
        sa.Column("category", sa.String(100)),
        sa.Column("rating", sa.Integer, default=5),
        sa.Column("contact_info", sa.JSON),
        sa.Column("test_methods", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "lab_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("lab_organizations.id")),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id")),
        sa.Column("request_type", sa.String(100)),
        sa.Column("status", sa.String(50), default="draft"),
        sa.Column("description", sa.Text),
        sa.Column("deadline", sa.DateTime),
        sa.Column("commercial_proposal", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        "lab_samples",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("lab_requests.id")),
        sa.Column("sample_type", sa.String(100)),
        sa.Column("sample_identifier", sa.String(100)),
        sa.Column("manufacture_date", sa.DateTime),
        sa.Column("delivery_date", sa.DateTime),
        sa.Column("test_date", sa.DateTime),
        sa.Column("test_method", sa.String(200)),
        sa.Column("result_value", sa.String(100)),
        sa.Column("result_status", sa.String(50)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "lab_contracts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("lab_organizations.id")),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id")),
        sa.Column("contract_number", sa.String(100)),
        sa.Column("contract_date", sa.DateTime),
        sa.Column("contract_value", sa.Integer),
        sa.Column("valid_until", sa.DateTime),
        sa.Column("status", sa.String(50), default="active"),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "lab_acts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contract_id", sa.Integer, sa.ForeignKey("lab_contracts.id")),
        sa.Column("act_number", sa.String(100)),
        sa.Column("act_date", sa.DateTime),
        sa.Column("act_value", sa.Integer),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(50), default="issued"),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "lab_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id")),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("lab_organizations.id")),
        sa.Column("report_number", sa.String(100)),
        sa.Column("report_date", sa.DateTime),
        sa.Column("report_type", sa.String(200)),
        sa.Column("conclusion", sa.Text),
        sa.Column("status", sa.String(50), default="received"),
        sa.Column("review_notes", sa.Text),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "lab_control_plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id")),
        sa.Column("plan_name", sa.String(255)),
        sa.Column("work_types", sa.JSON),
        sa.Column("test_schedule", sa.JSON),
        sa.Column("status", sa.String(50), default="draft"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── Опытный контур — Lessons Learned ──
    op.create_table(
        "lessons_learned",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("lot_number", sa.String(50)),
        sa.Column("work_type", sa.String(100)),
        sa.Column("agent_name", sa.String(50)),
        sa.Column("category", sa.String(50)),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("severity", sa.String(20)),
        sa.Column("norm_reference", sa.String(512)),
        sa.Column("lot_context", sa.JSON),
        sa.Column("verified", sa.Boolean, default=False),
        sa.Column("verification_count", sa.Integer, default=0),
        sa.Column("auto_rule", sa.Boolean, default=False),
        sa.Column("auto_rule_text", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("embedding", Vector(1024)),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    tables = [
        "lessons_learned",
        "lab_control_plans",
        "lab_reports",
        "lab_acts",
        "lab_contracts",
        "lab_samples",
        "lab_requests",
        "lab_organizations",
        "price_list_items",
        "price_lists",
        "materials_catalog",
        "vendors",
        "domain_traps",
        "audit_logs",
        "document_chunks",
        "documents",
        "projects",
    ]
    for table in tables:
        op.drop_table(table)

    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
