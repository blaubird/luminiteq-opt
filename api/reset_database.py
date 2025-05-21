"""
Скрипт для полного сброса и пересоздания схемы базы данных
"""
import os
import sys
import logging
from sqlalchemy import create_engine, text
from alembic.config import Config
from alembic import command

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def drop_all_tables():
    """Удаляет все таблицы из базы данных."""
    try:
        # Получаем URL базы данных из переменной окружения
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("Переменная окружения DATABASE_URL не установлена")
            return False
        
        # Создаем движок SQLAlchemy
        engine = create_engine(database_url)
        
        # Удаляем все таблицы
        with engine.connect() as conn:
            logger.info("Получаем список всех таблиц...")
            result = conn.execute(text("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public'
            """))
            tables = [row[0] for row in result.fetchall()]
            logger.info(f"Найденные таблицы: {tables}")
            
            # Отключаем проверку внешних ключей
            conn.execute(text("SET session_replication_role = 'replica';"))
            
            # Удаляем все таблицы
            for table in tables:
                logger.info(f"Удаляем таблицу {table}...")
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
            
            # Включаем проверку внешних ключей
            conn.execute(text("SET session_replication_role = 'origin';"))
            conn.commit()
            
            logger.info("Все таблицы успешно удалены")
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении таблиц: {str(e)}")
        return False

def activate_pgvector():
    """Активирует расширение pgvector в PostgreSQL."""
    try:
        # Получаем URL базы данных из переменной окружения
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("Переменная окружения DATABASE_URL не установлена")
            return False
        
        # Создаем движок SQLAlchemy
        engine = create_engine(database_url)
        
        # Активируем расширение pgvector
        with engine.connect() as conn:
            logger.info("Активируем расширение pgvector...")
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
            logger.info("Расширение pgvector успешно активировано!")
        return True
    except Exception as e:
        logger.error(f"Ошибка при активации расширения pgvector: {str(e)}")
        return False

def create_initial_migration():
    """Создает начальную миграцию Alembic."""
    try:
        # Получаем путь к alembic.ini
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alembic_ini_path = os.path.join(script_dir, "alembic.ini")
        
        if not os.path.exists(alembic_ini_path):
            logger.error(f"Файл alembic.ini не найден по пути: {alembic_ini_path}")
            return False
        
        # Создаем конфигурацию Alembic
        alembic_cfg = Config(alembic_ini_path)
        
        # Удаляем все файлы миграций
        versions_dir = os.path.join(script_dir, "alembic", "versions")
        if os.path.exists(versions_dir):
            for file in os.listdir(versions_dir):
                if file.endswith(".py"):
                    os.remove(os.path.join(versions_dir, file))
                    logger.info(f"Удален файл миграции: {file}")
        
        # Создаем новую миграцию
        logger.info("Создаем новую начальную миграцию...")
        command.revision(alembic_cfg, autogenerate=True, message="Initial migration")
        logger.info("Начальная миграция успешно создана!")
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании начальной миграции: {str(e)}")
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
        
        # Создаем конфигурацию Alembic
        alembic_cfg = Config(alembic_ini_path)
        
        # Применяем миграции
        logger.info("Применяем миграции Alembic...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Миграции успешно применены!")
        return True
    except Exception as e:
        logger.error(f"Ошибка при применении миграций: {str(e)}")
        return False

def create_test_tenant():
    """Создает тестового арендатора, если он не существует."""
    try:
        from sqlalchemy.orm import sessionmaker
        from models import Tenant
        
        # Получаем URL базы данных из переменной окружения
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("Переменная окружения DATABASE_URL не установлена")
            return False
        
        # Создаем движок SQLAlchemy и сессию
        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Проверяем, существует ли тестовый арендатор
        phone_id = os.getenv("WH_PHONE_ID", "565265096681520")
        tenant = session.query(Tenant).filter_by(phone_id=phone_id).first()
        
        if tenant:
            logger.info(f"Тестовый арендатор с phone_id={phone_id} уже существует")
            return True
        
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
        logger.info(f"Создан тестовый арендатор с phone_id={phone_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании тестового арендатора: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Запуск скрипта для полного сброса и пересоздания схемы базы данных")
    
    # Удаляем все таблицы
    if not drop_all_tables():
        logger.error("Не удалось удалить таблицы")
        sys.exit(1)
    
    # Активируем расширение pgvector
    if not activate_pgvector():
        logger.error("Не удалось активировать расширение pgvector")
        sys.exit(1)
    
    # Создаем начальную миграцию
    if not create_initial_migration():
        logger.error("Не удалось создать начальную миграцию")
        sys.exit(1)
    
    # Применяем миграции
    if not apply_migrations():
        logger.error("Не удалось применить миграции")
        sys.exit(1)
    
    # Создаем тестового арендатора
    if not create_test_tenant():
        logger.error("Не удалось создать тестового арендатора")
        sys.exit(1)
    
    logger.info("Схема базы данных успешно пересоздана, миграции применены, тестовый арендатор создан")
    sys.exit(0)
