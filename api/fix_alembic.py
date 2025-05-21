"""
Скрипт для исправления проблем с миграциями Alembic
"""
import os
import sys
import logging
import shutil
from pathlib import Path

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_alembic_env():
    """Исправляет файл env.py для корректной работы autogenerate."""
    try:
        # Путь к файлу env.py
        script_dir = os.path.dirname(os.path.abspath(__file__))
        env_py_path = os.path.join(script_dir, "alembic", "env.py")
        
        if not os.path.exists(env_py_path):
            logger.error(f"Файл env.py не найден по пути: {env_py_path}")
            return False
        
        # Создаем резервную копию
        backup_path = env_py_path + ".bak"
        shutil.copy2(env_py_path, backup_path)
        logger.info(f"Создана резервная копия env.py: {backup_path}")
        
        # Читаем содержимое файла
        with open(env_py_path, "r") as f:
            content = f.read()
        
        # Исправляем импорты и настройки target_metadata
        new_content = """
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import MetaData

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем все модели для autogenerate
from models import Base

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    \"\"\"Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    \"\"\"
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    \"\"\"Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    \"\"\"
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"""
        
        # Записываем новое содержимое
        with open(env_py_path, "w") as f:
            f.write(new_content)
        
        logger.info("Файл env.py успешно исправлен")
        return True
    except Exception as e:
        logger.error(f"Ошибка при исправлении файла env.py: {str(e)}")
        return False

def fix_alembic_ini():
    """Исправляет файл alembic.ini для корректной работы с переменными окружения."""
    try:
        # Путь к файлу alembic.ini
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alembic_ini_path = os.path.join(script_dir, "alembic.ini")
        
        if not os.path.exists(alembic_ini_path):
            logger.error(f"Файл alembic.ini не найден по пути: {alembic_ini_path}")
            return False
        
        # Создаем резервную копию
        backup_path = alembic_ini_path + ".bak"
        shutil.copy2(alembic_ini_path, backup_path)
        logger.info(f"Создана резервная копия alembic.ini: {backup_path}")
        
        # Читаем содержимое файла
        with open(alembic_ini_path, "r") as f:
            content = f.readlines()
        
        # Исправляем строку с URL базы данных
        for i, line in enumerate(content):
            if line.startswith("sqlalchemy.url = "):
                content[i] = "sqlalchemy.url = %(DATABASE_URL)s\n"
                break
        
        # Записываем новое содержимое
        with open(alembic_ini_path, "w") as f:
            f.writelines(content)
        
        logger.info("Файл alembic.ini успешно исправлен")
        return True
    except Exception as e:
        logger.error(f"Ошибка при исправлении файла alembic.ini: {str(e)}")
        return False

def create_manual_migration():
    """Создает ручную миграцию вместо autogenerate."""
    try:
        # Путь к директории с миграциями
        script_dir = os.path.dirname(os.path.abspath(__file__))
        versions_dir = os.path.join(script_dir, "alembic", "versions")
        
        # Создаем директорию, если она не существует
        os.makedirs(versions_dir, exist_ok=True)
        
        # Имя файла миграции
        migration_file = os.path.join(versions_dir, "001_initial_schema.py")
        
        # Содержимое миграции
        migration_content = """\"\"\"Initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-05-21 12:00:00.000000

\"\"\"
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Активируем расширение pgvector
    op.execute('CREATE EXTENSION IF NOT EXISTS vector;')
    
    # Создаем enum для ролей сообщений
    op.execute("CREATE TYPE role_enum AS ENUM ('user', 'assistant', 'system');")
    
    # Создаем таблицу tenants
    op.create_table('tenants',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('phone_id', sa.String(), nullable=False),
        sa.Column('wh_token', sa.String(), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tenants_id', 'tenants', ['id'], unique=False)
    
    # Создаем таблицу messages
    op.create_table('messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True),
        sa.Column('role', sa.Enum('user', 'assistant', 'system', name='role_enum'), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('ts', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_messages_tenant_id', 'messages', ['tenant_id'], unique=False)
    
    # Создаем таблицу faqs
    op.create_table('faqs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_faqs_tenant_id', 'faqs', ['tenant_id'], unique=False)


def downgrade() -> None:
    # Удаляем таблицы
    op.drop_index('ix_faqs_tenant_id', table_name='faqs')
    op.drop_table('faqs')
    op.drop_index('ix_messages_tenant_id', table_name='messages')
    op.drop_table('messages')
    op.drop_index('ix_tenants_id', table_name='tenants')
    op.drop_table('tenants')
    
    # Удаляем enum
    op.execute("DROP TYPE role_enum;")
    
    # Удаляем расширение pgvector
    op.execute('DROP EXTENSION IF EXISTS vector;')
"""
        
        # Записываем миграцию
        with open(migration_file, "w") as f:
            f.write(migration_content)
        
        logger.info(f"Ручная миграция создана: {migration_file}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании ручной миграции: {str(e)}")
        return False

def drop_all_tables():
    """Удаляет все таблицы из базы данных."""
    try:
        # Получаем URL базы данных из переменной окружения
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("Переменная окружения DATABASE_URL не установлена")
            return False
        
        # Создаем SQL-скрипт для удаления всех таблиц
        drop_script = """
import os
import psycopg2

# Получаем URL базы данных из переменной окружения
database_url = os.getenv("DATABASE_URL")

# Подключаемся к базе данных
conn = psycopg2.connect(database_url)
conn.autocommit = True
cursor = conn.cursor()

# Отключаем проверку внешних ключей
cursor.execute("SET session_replication_role = 'replica';")

# Получаем список всех таблиц
cursor.execute(\"\"\"
    SELECT tablename FROM pg_tables 
    WHERE schemaname = 'public'
\"\"\")
tables = [row[0] for row in cursor.fetchall()]
print(f"Найденные таблицы: {tables}")

# Удаляем все таблицы
for table in tables:
    print(f"Удаляем таблицу {table}...")
    cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")

# Получаем список всех типов
cursor.execute(\"\"\"
    SELECT typname FROM pg_type 
    WHERE typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
    AND typtype = 'e'
\"\"\")
types = [row[0] for row in cursor.fetchall()]
print(f"Найденные типы: {types}")

# Удаляем все типы
for type_name in types:
    print(f"Удаляем тип {type_name}...")
    cursor.execute(f"DROP TYPE IF EXISTS {type_name} CASCADE;")

# Включаем проверку внешних ключей
cursor.execute("SET session_replication_role = 'origin';")

# Закрываем соединение
cursor.close()
conn.close()

print("Все таблицы и типы успешно удалены")
"""
        
        # Записываем скрипт во временный файл
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drop_tables.py")
        with open(script_path, "w") as f:
            f.write(drop_script)
        
        # Запускаем скрипт
        logger.info("Запускаем скрипт для удаления всех таблиц...")
        os.system(f"python {script_path}")
        
        # Удаляем временный файл
        os.remove(script_path)
        
        logger.info("Все таблицы успешно удалены")
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении таблиц: {str(e)}")
        return False

def apply_migrations():
    """Применяет миграции Alembic к базе данных."""
    try:
        # Получаем путь к alembic.ini
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alembic_ini_path = os.path.join(script_dir, "alembic.ini")
        
        if not os.path.exists(alembic_ini_path):
            logger.error(f"Файл alembic.ini не найден по пути: {alembic_ini_path}")
            return False
        
        # Создаем скрипт для применения миграций
        apply_script = """
import os
import sys
from alembic.config import Config
from alembic import command

# Получаем путь к alembic.ini
alembic_ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")

# Создаем конфигурацию Alembic
alembic_cfg = Config(alembic_ini_path)

# Применяем миграции
print("Применяем миграции Alembic...")
command.upgrade(alembic_cfg, "head")
print("Миграции успешно применены!")
"""
        
        # Записываем скрипт во временный файл
        script_path = os.path.join(script_dir, "apply_migrations.py")
        with open(script_path, "w") as f:
            f.write(apply_script)
        
        # Запускаем скрипт
        logger.info("Запускаем скрипт для применения миграций...")
        os.system(f"python {script_path}")
        
        # Удаляем временный файл
        os.remove(script_path)
        
        logger.info("Миграции успешно применены")
        return True
    except Exception as e:
        logger.error(f"Ошибка при применении миграций: {str(e)}")
        return False

def create_test_tenant():
    """Создает тестового арендатора."""
    try:
        # Создаем скрипт для создания тестового арендатора
        tenant_script = """
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import Tenant

# Получаем URL базы данных из переменной окружения
database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("Переменная окружения DATABASE_URL не установлена")
    sys.exit(1)

# Создаем движок SQLAlchemy и сессию
engine = create_engine(database_url)
Session = sessionmaker(bind=engine)
session = Session()

# Проверяем, существует ли тестовый арендатор
phone_id = os.getenv("WH_PHONE_ID", "565265096681520")
tenant = session.query(Tenant).filter_by(phone_id=phone_id).first()

if tenant:
    print(f"Тестовый арендатор с phone_id={phone_id} уже существует")
    sys.exit(0)

# Создаем тестового арендатора
wh_token = os.getenv("WH_TOKEN", "test_token")
new_tenant = Tenant(
    id="test_tenant",
    phone_id=phone_id,
    wh_token=wh_token,
    system_prompt="You are a helpful assistant."
)

session.add(new_tenant)
session.commit()
print(f"Создан тестовый арендатор с phone_id={phone_id}")
"""
        
        # Записываем скрипт во временный файл
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, "create_tenant.py")
        with open(script_path, "w") as f:
            f.write(tenant_script)
        
        # Запускаем скрипт
        logger.info("Запускаем скрипт для создания тестового арендатора...")
        os.system(f"python {script_path}")
        
        # Удаляем временный файл
        os.remove(script_path)
        
        logger.info("Тестовый арендатор успешно создан")
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании тестового арендатора: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Запуск скрипта для исправления проблем с миграциями Alembic")
    
    # Исправляем файл env.py
    if not fix_alembic_env():
        logger.error("Не удалось исправить файл env.py")
        sys.exit(1)
    
    # Исправляем файл alembic.ini
    if not fix_alembic_ini():
        logger.error("Не удалось исправить файл alembic.ini")
        sys.exit(1)
    
    # Создаем ручную миграцию
    if not create_manual_migration():
        logger.error("Не удалось создать ручную миграцию")
        sys.exit(1)
    
    # Удаляем все таблицы
    if not drop_all_tables():
        logger.error("Не удалось удалить таблицы")
        sys.exit(1)
    
    # Применяем миграции
    if not apply_migrations():
        logger.error("Не удалось применить миграции")
        sys.exit(1)
    
    # Создаем тестового арендатора
    if not create_test_tenant():
        logger.error("Не удалось создать тестового арендатора")
        sys.exit(1)
    
    logger.info("Все проблемы с миграциями Alembic успешно исправлены")
    sys.exit(0)
