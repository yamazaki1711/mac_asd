"""MAC_ASD v12.0 — HNSW vector indexes for pgvector.

Revision ID: v12_0_hnsw
Revises: v12_0_initial
Create Date: 2026-05-04

Adds HNSW indexes on all embedding(1024) columns for sub-linear
approximate nearest neighbour search. Without these indexes pgvector
falls back to brute-force exact search (O(n) per query).

Tables indexed:
  - document_chunks   (RAG chunk retrieval)
  - domain_traps      (knowledge base search)
  - materials_catalog (material fuzzy matching)
  - lessons_learned   (lessons retrieval)
  - domain_references (normative reference search)
"""
from typing import Sequence, Union

from alembic import op

revision: str = "v12_0_hnsw"
down_revision: Union[str, None] = "v12_0_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


HNSW_INDEXES = [
    ("ix_document_chunks_embedding", "document_chunks"),
    ("ix_domain_traps_embedding", "domain_traps"),
    ("ix_materials_catalog_embedding", "materials_catalog"),
    ("ix_lessons_learned_embedding", "lessons_learned"),
    ("ix_domain_references_embedding", "domain_references"),
]


def upgrade() -> None:
    for idx_name, table in HNSW_INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} "
            f"ON {table} USING hnsw (embedding vector_cosine_ops);"
        )


def downgrade() -> None:
    for idx_name, _ in HNSW_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {idx_name};")
