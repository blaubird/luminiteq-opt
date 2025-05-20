"""Initial migration - creates tenants and messages tables

Revision ID: 0001_initial
Revises: 
Create Date: 2025-05-19 10:01:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    """
    Creates the initial database schema with tenants and messages tables.
    """
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('phone_id', sa.String(), unique=True, nullable=False),
        sa.Column('wh_token', sa.Text(), nullable=False),
        sa.Column('system_prompt', sa.Text(), server_default='You are a helpful assistant.'),
    )
    
    # Create messages table with foreign key to tenants
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), index=True),
        sa.Column('wa_msg_id', sa.String(), unique=True),
        sa.Column('role', sa.Enum('user','assistant', name='role_enum')),
        sa.Column('text', sa.Text()),
        sa.Column('ts', sa.DateTime(), server_default=sa.func.now()),
    )

def downgrade():
    """
    Drops the messages and tenants tables in the correct order to maintain referential integrity.
    """
    op.drop_table('messages')
    op.drop_table('tenants')
