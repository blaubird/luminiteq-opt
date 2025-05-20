"""
Модуль для настройки и экспорта метрик в Grafana Cloud.
"""
import os
import time
from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import CollectorRegistry, multiprocess
from starlette.responses import Response

# Создаем реестр метрик
registry = CollectorRegistry()

# Определяем метрики
http_requests_total = Counter(
    'http_requests_total', 
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status_code'],
    registry=registry
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    registry=registry
)

openai_api_calls_total = Counter(
    'openai_api_calls_total',
    'Total number of OpenAI API calls',
    ['model', 'endpoint'],
    registry=registry
)

openai_api_duration_seconds = Histogram(
    'openai_api_duration_seconds',
    'OpenAI API call duration in seconds',
    ['model', 'endpoint'],
    registry=registry
)

openai_api_tokens_total = Counter(
    'openai_api_tokens_total',
    'Total number of tokens used in OpenAI API calls',
    ['model', 'type'],  # type: prompt, completion
    registry=registry
)

celery_tasks_total = Counter(
    'celery_tasks_total',
    'Total number of Celery tasks',
    ['task_name', 'status'],  # status: started, success, failure
    registry=registry
)

celery_task_duration_seconds = Histogram(
    'celery_task_duration_seconds',
    'Celery task duration in seconds',
    ['task_name'],
    registry=registry
)

active_tenants_gauge = Gauge(
    'active_tenants',
    'Number of active tenants',
    registry=registry
)

active_users_gauge = Gauge(
    'active_users',
    'Number of active users in the last 24 hours',
    registry=registry
)

class PrometheusMiddleware:
    """
    Middleware для сбора метрик HTTP-запросов
    """
    def __init__(self, app: FastAPI):
        self.app = app

    async def __call__(self, request: Request, call_next):
        start_time = time.time()
        
        # Обрабатываем запрос
        response = await call_next(request)
        
        # Измеряем время выполнения
        duration = time.time() - start_time
        
        # Получаем endpoint (без параметров запроса)
        endpoint = request.url.path
        
        # Инкрементируем счетчик запросов
        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code
        ).inc()
        
        # Записываем время выполнения
        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(duration)
        
        return response

def setup_metrics(app: FastAPI):
    """
    Настройка сбора метрик для FastAPI приложения
    """
    # Добавляем middleware для сбора метрик HTTP-запросов
    app.add_middleware(PrometheusMiddleware)
    
    # Добавляем endpoint для экспорта метрик
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(
            content=generate_latest(registry),
            media_type=CONTENT_TYPE_LATEST
        )
    
    # Инициализируем метрики при запуске
    @app.on_event("startup")
    async def startup_metrics():
        # Инициализация метрик, которые требуют данных из БД
        # Например, количество активных тенантов
        pass

def track_openai_call(model: str, endpoint: str):
    """
    Декоратор для отслеживания вызовов OpenAI API
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            # Инкрементируем счетчик вызовов API
            openai_api_calls_total.labels(
                model=model,
                endpoint=endpoint
            ).inc()
            
            try:
                # Выполняем оригинальную функцию
                result = await func(*args, **kwargs)
                
                # Если есть информация о токенах, записываем ее
                if hasattr(result, 'usage') and result.usage:
                    if hasattr(result.usage, 'prompt_tokens'):
                        openai_api_tokens_total.labels(
                            model=model,
                            type='prompt'
                        ).inc(result.usage.prompt_tokens)
                    
                    if hasattr(result.usage, 'completion_tokens'):
                        openai_api_tokens_total.labels(
                            model=model,
                            type='completion'
                        ).inc(result.usage.completion_tokens)
                
                return result
            finally:
                # Записываем время выполнения
                duration = time.time() - start_time
                openai_api_duration_seconds.labels(
                    model=model,
                    endpoint=endpoint
                ).observe(duration)
        
        return wrapper
    
    return decorator

def track_celery_task(task_name: str):
    """
    Декоратор для отслеживания выполнения Celery-задач
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            # Инкрементируем счетчик запущенных задач
            celery_tasks_total.labels(
                task_name=task_name,
                status='started'
            ).inc()
            
            try:
                # Выполняем оригинальную функцию
                result = func(*args, **kwargs)
                
                # Инкрементируем счетчик успешных задач
                celery_tasks_total.labels(
                    task_name=task_name,
                    status='success'
                ).inc()
                
                return result
            except Exception as e:
                # Инкрементируем счетчик неудачных задач
                celery_tasks_total.labels(
                    task_name=task_name,
                    status='failure'
                ).inc()
                
                # Пробрасываем исключение дальше
                raise
            finally:
                # Записываем время выполнения
                duration = time.time() - start_time
                celery_task_duration_seconds.labels(
                    task_name=task_name
                ).observe(duration)
        
        return wrapper
    
    return decorator

def update_active_tenants(count: int):
    """
    Обновляет метрику активных тенантов
    """
    active_tenants_gauge.set(count)

def update_active_users(count: int):
    """
    Обновляет метрику активных пользователей
    """
    active_users_gauge.set(count)
