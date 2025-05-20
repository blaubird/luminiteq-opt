"""Add FAQ table with pgvector support

Revision ID: 0002_add_faq_table_with_vector
Revises: 0001_initial
Create Date: 2025-05-19 10:02:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '0002_add_faq_table_with_vector'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Creates the FAQ table with pgvector support for embeddings.
    This combines the previously separate migrations:
    - manual_add_faq_table.py (creating the table with LargeBinary)
    - 699f48bb78e6_change_faq_embedding_to_vector_type.py (changing to Vector)
    
    The table is created directly with Vector(1536) type for embeddings.
    """
    # Create the FAQ table with Vector(1536) for embeddings
    op.create_table('faqs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('ts', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for better performance
    op.create_index(op.f('ix_faqs_tenant_id'), 'faqs', ['tenant_id'], unique=False)
    
    # Create an index for vector similarity search
    op.execute('CREATE INDEX idx_faqs_embedding ON faqs USING ivfflat (embedding vector_cosine_ops)')


def downgrade() -> None:
    """
    Drops the FAQ table and all associated indexes.
    """
    # Drop all indexes first
    op.drop_index('idx_faqs_embedding', table_name='faqs')
    op.drop_index(op.f('ix_faqs_tenant_id'), table_name='faqs')
    
    # Drop the table
    op.drop_table('faqs')
