"""change_faq_embedding_to_vector_type

Revision ID: 699f48bb78e6
Revises: manual_faq_creation
Create Date: 2025-05-15 11:33:23.099619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector # Import Vector


# revision identifiers, used by Alembic.
revision: str = '699f48bb78e6'
down_revision: Union[str, None] = 'manual_faq_creation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to change embedding column type by dropping and recreating."""
    op.drop_column('faqs', 'embedding')
    op.add_column('faqs', sa.Column('embedding', Vector(1536), nullable=True))


def downgrade() -> None:
    """Downgrade schema to revert embedding column type by dropping and recreating."""
    op.drop_column('faqs', 'embedding')
    op.add_column('faqs', sa.Column('embedding', sa.LargeBinary(), nullable=True))


