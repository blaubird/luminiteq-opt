import time
import functools
import os
from prometheus_client import Counter, Histogram, start_http_server

# Метрики Prometheus
OPENAI_CALLS = Counter(
    'openai_api_calls_total', 
    'Total number of OpenAI API calls',
    ['model', 'endpoint', 'status']
)

OPENAI_LATENCY = Histogram(
    'openai_api_latency_seconds',
    'Latency of OpenAI API calls in seconds',
    ['model', 'endpoint'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
)

def setup_monitoring(app):
    """
    Настраивает мониторинг для FastAPI приложения.
    Запускает HTTP-сервер Prometheus на порту, указанном в переменной окружения
    PROMETHEUS_PORT (по умолчанию 9090).
    """
    # Получаем порт из переменной окружения или используем 9090 по умолчанию
    prometheus_port = int(os.getenv("PROMETHEUS_PORT", 9090))
    
    try:
        # Запускаем HTTP-сервер для метрик Prometheus
        start_http_server(prometheus_port)
    except OSError as e:
        # Если порт занят, пробуем использовать другой порт
        if e.errno == 98:  # Address already in use
            fallback_port = prometheus_port + 1
            print(f"Port {prometheus_port} is already in use. Trying port {fallback_port}")
            start_http_server(fallback_port)
    
    # Добавляем middleware для отслеживания запросов FastAPI
    @app.middleware("http")
    async def add_process_time_header(request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response
    
    return app

def track_openai_call(model, endpoint):
    """
    Декоратор для отслеживания вызовов OpenAI API.
    Записывает метрики в Prometheus.
    
    Args:
        model: Название модели OpenAI (например, "gpt-4")
        endpoint: Название эндпоинта API (например, "chat/completions")
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                OPENAI_CALLS.labels(model=model, endpoint=endpoint, status="success").inc()
                return result
            except Exception as e:
                OPENAI_CALLS.labels(model=model, endpoint=endpoint, status="error").inc()
                raise e
            finally:
                end_time = time.time()
                OPENAI_LATENCY.labels(model=model, endpoint=endpoint).observe(end_time - start_time)
        return wrapper
    return decorator
