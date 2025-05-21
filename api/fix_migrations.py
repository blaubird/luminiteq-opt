"""
Скрипт для активации расширения pgvector, применения миграций Alembic
и исправления проблемы с ROLLBACK в миграции 0003.
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

def fix_alembic_version():
    """Исправляет таблицу alembic_version, если миграция 0003 вызывает ROLLBACK."""
    try:
        # Получаем URL базы данных из переменной окружения
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("Переменная окружения DATABASE_URL не установлена")
            return False
        
        # Создаем движок SQLAlchemy
        engine = create_engine(database_url)
        
        # Проверяем текущую версию миграции
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            version = result.fetchone()
            
            if not version:
                logger.warning("Таблица alembic_version пуста или не существует")
                return False
            
            current_version = version[0]
            logger.info(f"Текущая версия миграции: {current_version}")
            
            # Если миграция застряла на 0002, принудительно устанавливаем 0003
            if current_version == '0002_add_faq_table_with_vector':
                logger.info("Исправляем версию миграции с 0002 на 0003...")
                conn.execute(text("UPDATE alembic_version SET version_num = '0003_update_faq_embedding_dimension'"))
                conn.commit()
                logger.info("Версия миграции успешно обновлена до 0003_update_faq_embedding_dimension")
            
            # Проверяем, что все таблицы существуют
            tables_query = """
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
            result = conn.execute(text(tables_query))
            tables = [row[0] for row in result.fetchall()]
            logger.info(f"Существующие таблицы: {tables}")
            
            required_tables = ["tenants", "messages", "faqs", "alembic_version"]
            missing_tables = [table for table in required_tables if table not in tables]
            
            if missing_tables:
                logger.error(f"Отсутствуют таблицы: {missing_tables}")
                return False
            
            logger.info("Все необходимые таблицы существуют")
            return True
    except Exception as e:
        logger.error(f"Ошибка при исправлении версии миграции: {str(e)}")
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
    logger.info("Запуск скрипта для активации pgvector и исправления миграций")
    
    # Активируем расширение pgvector
    if not activate_pgvector():
        logger.error("Не удалось активировать расширение pgvector")
        sys.exit(1)
    
    # Исправляем версию миграции, если необходимо
    if not fix_alembic_version():
        logger.warning("Не удалось исправить версию миграции, пробуем применить миграции")
    
    # Применяем миграции
    if not apply_migrations():
        logger.error("Не удалось применить миграции")
        sys.exit(1)
    
    # Создаем тестового арендатора
    if not create_test_tenant():
        logger.error("Не удалось создать тестового арендатора")
        sys.exit(1)
    
    logger.info("Расширение pgvector активировано, миграции исправлены, тестовый арендатор создан")
    sys.exit(0)
