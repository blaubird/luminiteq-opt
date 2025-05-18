-- Миграция для изменения размерности embedding в таблице faqs
-- Файл: api/alembic/versions/change_faq_embedding_dimension.py

"""Change FAQ embedding dimension to 384

Revision ID: change_faq_embedding_dimension
Revises: 699f48bb78e6
Create Date: 2025-05-17

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = 'change_faq_embedding_dimension'
down_revision = '699f48bb78e6'
branch_labels = None
depends_on = None

def upgrade():
    # Создаем временную таблицу с новой размерностью
    op.execute('CREATE TABLE faqs_new (LIKE faqs INCLUDING ALL EXCLUDING CONSTRAINTS EXCLUDING INDEXES)')
    
    # Изменяем тип столбца embedding в новой таблице
    op.execute('ALTER TABLE faqs_new ALTER COLUMN embedding TYPE vector(384)')
    
    # Копируем данные из старой таблицы (без эмбеддингов, так как они несовместимы)
    op.execute('INSERT INTO faqs_new (id, tenant_id, question, answer, ts) SELECT id, tenant_id, question, answer, ts FROM faqs')
    
    # Удаляем старую таблицу и переименовываем новую
    op.execute('DROP TABLE faqs')
    op.execute('ALTER TABLE faqs_new RENAME TO faqs')
    
    # Воссоздаем индексы и ограничения
    op.create_primary_key('faqs_pkey', 'faqs', ['id'])
    op.create_index('idx_faqs_tenant_id', 'faqs', ['tenant_id'])
    op.create_index('idx_faqs_embedding', 'faqs', ['embedding'], postgresql_using='ivfflat')

def downgrade():
    # Создаем временную таблицу с исходной размерностью
    op.execute('CREATE TABLE faqs_old (LIKE faqs INCLUDING ALL EXCLUDING CONSTRAINTS EXCLUDING INDEXES)')
    
    # Изменяем тип столбца embedding в новой таблице
    op.execute('ALTER TABLE faqs_old ALTER COLUMN embedding TYPE vector(1536)')
    
    # Копируем данные из текущей таблицы (без эмбеддингов, так как они несовместимы)
    op.execute('INSERT INTO faqs_old (id, tenant_id, question, answer, ts) SELECT id, tenant_id, question, answer, ts FROM faqs')
    
    # Удаляем текущую таблицу и переименовываем старую
    op.execute('DROP TABLE faqs')
    op.execute('ALTER TABLE faqs_old RENAME TO faqs')
    
    # Воссоздаем индексы и ограничения
    op.create_primary_key('faqs_pkey', 'faqs', ['id'])
    op.create_index('idx_faqs_tenant_id', 'faqs', ['tenant_id'])
    op.create_index('idx_faqs_embedding', 'faqs', ['embedding'], postgresql_using='ivfflat')

