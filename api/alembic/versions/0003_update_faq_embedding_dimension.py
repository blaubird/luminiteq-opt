"""Update FAQ embedding dimension to 1536

Revision ID: 0003_update_faq_embedding_dimension
Revises: 0002_add_faq_table_with_vector
Create Date: 2025-05-19 10:02:30.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '0003_update_faq_embedding_dimension'
down_revision = '0002_add_faq_table_with_vector'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    This migration is a placeholder for future dimension changes.
    
    The previous migration chain had inconsistencies with embedding dimensions:
    - First creating with LargeBinary
    - Then changing to Vector(1536)
    - Then attempting to change to Vector(384)
    
    Since we've standardized on Vector(1536) in the previous migration,
    this migration serves as a reference point for any future dimension changes.
    It also documents the decision to use 1536 dimensions (OpenAI's text-embedding-ada-002).
    """
    # No actual changes needed as we've already set Vector(1536) in the previous migration
    op.execute('SELECT 1')  # No-op SQL statement


def downgrade() -> None:
    """
    No changes to revert.
    """
    # No actual changes to revert
    op.execute('SELECT 1')  # No-op SQL statement
