from celery import Celery
import os
import logging
import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import Session
from models import Message, Tenant

# Настройка логирования
logger = logging.getLogger(__name__)

# Инициализация Celery
celery_app = Celery('luminiteq_tasks')
celery_app.conf.broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
celery_app.conf.result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

# Проверка и логирование конфигурации Redis
redis_host = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
logger.info(f"Celery configured with broker: {redis_host}")

# Настройка ограничений и повторных попыток
celery_app.conf.task_acks_late = True  # Подтверждение задачи только после успешного выполнения
celery_app.conf.task_reject_on_worker_lost = True  # Перезапуск задачи при потере воркера
celery_app.conf.task_time_limit = 300  # Ограничение времени выполнения (5 минут)
celery_app.conf.task_soft_time_limit = 240  # Мягкое ограничение (4 минуты)
celery_app.conf.worker_concurrency = 4  # Количество параллельных воркеров
celery_app.conf.task_default_retry_delay = 60  # Задержка перед повторной попыткой (60 секунд)
celery_app.conf.task_max_retries = 3  # Максимальное количество повторных попыток
celery_app.conf.broker_connection_retry = True  # Автоматические повторные попытки подключения к брокеру
celery_app.conf.broker_connection_retry_on_startup = True  # Повторные попытки при запуске
celery_app.conf.broker_connection_max_retries = 10  # Максимальное количество повторных попыток подключения

@celery_app.task(bind=True, name='tasks.process_ai_reply')
def process_ai_reply(self, tenant_id, tenant_phone_id, tenant_wh_token, tenant_system_prompt, 
                    chat_context, sender_phone, message_id):
    """
    Celery-задача для обработки AI-ответа и отправки его в WhatsApp.
    Заменяет асинхронную функцию handle_ai_reply из main.py.
    """
    from deps import get_db
    
    db = None
    try:
        # Получаем сессию БД
        db = next(get_db())
        logger.info(f"Celery task: Generating AI reply for tenant {tenant_id} to {sender_phone}")
        
        # Проверяем API ключ
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY not available in Celery task.")
            raise self.retry(countdown=30, max_retries=3)
        
        # Инициализируем клиент OpenAI
        ai_client = AsyncOpenAI(api_key=api_key.strip())
        
        # Получаем ответ от OpenAI (синхронная версия для Celery)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def get_ai_response():
            return await ai_client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                messages=chat_context
            )
        
        response = loop.run_until_complete(get_ai_response())
        ai_answer = response.choices[0].message.content
        loop.close()
        
        logger.info(f"Celery task: AI generated answer: '{ai_answer[:100]}...'")
        
        # Сохраняем ответ в БД
        db_ai_message = Message(
            tenant_id=tenant_id,
            role="assistant",
            text=ai_answer
        )
        db.add(db_ai_message)
        db.commit()
        logger.info(f"Celery task: Saved AI response for tenant {tenant_id}")
        
        # Отправляем ответ в WhatsApp
        if not tenant_wh_token:
            logger.error(f"WhatsApp token not available for tenant {tenant_id} in Celery task.")
            return
        
        # Используем синхронный клиент для Celery
        with httpx.Client() as client:
            send_url = f"https://graph.facebook.com/v{os.getenv('FB_GRAPH_VERSION', '19.0')}/{tenant_phone_id}/messages"
            headers = {
                "Authorization": f"Bearer {tenant_wh_token}",
                "Content-Type": "application/json",
            }
            json_payload = {
                "messaging_product": "whatsapp",
                "to": sender_phone,
                "type": "text",
                "text": {"body": ai_answer},
            }
            
            send_response = client.post(send_url, headers=headers, json=json_payload)
            logger.info(f"Celery task: WhatsApp API response status {send_response.status_code} for tenant {tenant_id}. Response: {send_response.text}")
            send_response.raise_for_status()
            
    except httpx.HTTPStatusError as e:
        logger.error(f"Celery task: HTTP error sending WhatsApp reply for tenant {tenant_id}: {e.response.text}", exc_info=True)
        raise self.retry(exc=e, countdown=60)
    except Exception as e:
        logger.error(f"Celery task: Error processing AI reply for tenant {tenant_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=30)
    finally:
        if db:
            db.close()

# Задача для массового импорта FAQ (перенесена из admin.py)
@celery_app.task(bind=True, name='tasks.process_bulk_faq_import')
def process_bulk_faq_import(self, tenant_id, import_items):
    """
    Celery-задача для обработки массового импорта FAQ.
    Заменяет асинхронную функцию process_bulk_faq_import из admin.py.
    """
    from deps import get_db
    from models import FAQ
    from ai import generate_embedding
    import asyncio
    
    db = None
    try:
        db = next(get_db())
        successful_count = 0
        failed_count = 0
        errors = []
        
        # Создаем event loop для асинхронных вызовов
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for item in import_items:
            try:
                # Генерируем embedding для FAQ
                content_to_embed = f"Question: {item['question']} Answer: {item['answer']}"
                embedding = loop.run_until_complete(generate_embedding(content_to_embed))
                
                if embedding is None:
                    logger.error(f"Failed to generate embedding for FAQ: Q: {item['question'][:50]}...")
                    failed_count += 1
                    errors.append({
                        "question": item['question'][:50] + "...",
                        "error": "Failed to generate embedding"
                    })
                    continue
                
                # Создаем новую запись FAQ
                new_faq = FAQ(
                    question=item['question'],
                    answer=item['answer'],
                    tenant_id=tenant_id,
                    embedding=embedding
                )
                db.add(new_faq)
                db.commit()
                successful_count += 1
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error importing FAQ: {str(e)}")
                failed_count += 1
                errors.append({
                    "question": item['question'][:50] + "...",
                    "error": str(e)
                })
        
        loop.close()
        logger.info(f"Bulk import completed for tenant {tenant_id}: {successful_count} successful, {failed_count} failed")
        
        # Возвращаем результат для отслеживания
        return {
            "tenant_id": tenant_id,
            "total_items": len(import_items),
            "successful_items": successful_count,
            "failed_items": failed_count,
            "errors": errors
        }
        
    except Exception as e:
        logger.error(f"Error in bulk import Celery task: {str(e)}")
        raise self.retry(exc=e, countdown=30)
    finally:
        if db:
            db.close()
