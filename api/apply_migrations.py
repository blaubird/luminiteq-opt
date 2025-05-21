"""
Скрипт для принудительного применения миграций Alembic
и проверки структуры базы данных.
"""
import os
import sys
from alembic.config import Config
from alembic import command
from sqlalchemy import inspect, create_engine
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def check_db_schema():
    """Проверяет структуру базы данных."""
    try:
        # Получаем URL базы данных из переменной окружения
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("Переменная окружения DATABASE_URL не установлена")
            return False
        
        # Создаем движок SQLAlchemy
        engine = create_engine(database_url)
        
        # Получаем инспектор для проверки схемы
        inspector = inspect(engine)
        
        # Проверяем наличие необходимых таблиц
        tables = inspector.get_table_names()
        logger.info(f"Найденные таблицы: {tables}")
        
        required_tables = ["tenants", "messages", "faqs", "alembic_version"]
        missing_tables = [table for table in required_tables if table not in tables]
        
        if missing_tables:
            logger.error(f"Отсутствуют таблицы: {missing_tables}")
            return False
        
        # Проверяем структуру таблицы tenants
        tenant_columns = {col['name'] for col in inspector.get_columns('tenants')}
        required_tenant_columns = {'id', 'phone_id', 'wh_token', 'system_prompt'}
        missing_tenant_columns = required_tenant_columns - tenant_columns
        
        if missing_tenant_columns:
            logger.error(f"В таблице tenants отсутствуют столбцы: {missing_tenant_columns}")
            return False
        
        logger.info("Структура базы данных соответствует требованиям")
        return True
    except Exception as e:
        logger.error(f"Ошибка при проверке структуры базы данных: {str(e)}")
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
    logger.info("Запуск скрипта для применения миграций и проверки структуры БД")
    
    # Применяем миграции
    if not apply_migrations():
        logger.error("Не удалось применить миграции")
        sys.exit(1)
    
    # Проверяем структуру БД
    if not check_db_schema():
        logger.error("Структура базы данных не соответствует требованиям")
        sys.exit(1)
    
    # Создаем тестового арендатора
    if not create_test_tenant():
        logger.error("Не удалось создать тестового арендатора")
        sys.exit(1)
    
    logger.info("Миграции применены, структура БД проверена, тестовый арендатор создан")
    sys.exit(0)
