import logging
import json
import time
import traceback
from typing import Dict, Any, Optional, Callable
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from contextvars import ContextVar

# Контекстная переменная для хранения request_id и других метаданных
request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})

class StructuredLogger:
    """
    Класс для структурированного логирования в формате JSON
    """
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _log(self, level: int, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        """Базовый метод логирования с добавлением контекста"""
        context = request_context.get()
        log_data = {
            "message": msg,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "level": logging.getLevelName(level),
        }
        
        # Добавляем контекст запроса, если есть
        if context:
            log_data.update(context)
        
        # Добавляем дополнительные поля
        if extra:
            log_data.update(extra)
        
        # Добавляем информацию об исключении, если есть
        if exc_info:
            if isinstance(exc_info, Exception):
                log_data["exception"] = {
                    "type": exc_info.__class__.__name__,
                    "message": str(exc_info),
                    "traceback": traceback.format_exc()
                }
            else:
                log_data["exc_info"] = True
        
        # Логируем как JSON
        self.logger.log(level, json.dumps(log_data), exc_info=exc_info if exc_info is True else None)
    
    def debug(self, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        self._log(logging.DEBUG, msg, extra, exc_info)
    
    def info(self, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        self._log(logging.INFO, msg, extra, exc_info)
    
    def warning(self, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        self._log(logging.WARNING, msg, extra, exc_info)
    
    def error(self, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        self._log(logging.ERROR, msg, extra, exc_info)
    
    def critical(self, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        self._log(logging.CRITICAL, msg, extra, exc_info)

def get_logger(name: str) -> StructuredLogger:
    """Фабричный метод для получения структурированного логгера"""
    return StructuredLogger(name)

class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware для добавления контекста запроса в логи
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Генерируем уникальный ID запроса
        request_id = f"{time.time()}-{id(request)}"
        
        # Создаем контекст запроса
        context = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else None,
        }
        
        # Устанавливаем контекст
        token = request_context.set(context)
        
        try:
            # Замеряем время выполнения запроса
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Добавляем информацию о времени выполнения и статусе ответа
            context = request_context.get()
            context.update({
                "status_code": response.status_code,
                "process_time_ms": round(process_time * 1000, 2)
            })
            request_context.reset(token)
            
            # Добавляем заголовок с ID запроса
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as e:
            # Логируем исключение
            logger = get_logger("middleware")
            logger.error(
                f"Unhandled exception in request: {str(e)}",
                extra={"exception_type": e.__class__.__name__},
                exc_info=e
            )
            # Пробрасываем исключение дальше для обработки глобальным обработчиком
            raise
        finally:
            # Сбрасываем контекст
            request_context.reset(token)

class GlobalExceptionHandler:
    """
    Глобальный обработчик исключений для FastAPI
    """
    def __init__(self, app: FastAPI):
        @app.exception_handler(Exception)
        async def handle_exception(request: Request, exc: Exception):
            # Получаем логгер
            logger = get_logger("exception_handler")
            
            # Логируем исключение
            logger.error(
                f"Unhandled exception: {str(exc)}",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "exception_type": exc.__class__.__name__
                },
                exc_info=exc
            )
            
            # Возвращаем ответ с ошибкой
            from fastapi.responses import JSONResponse
            from fastapi import status
            
            # Определяем статус код в зависимости от типа исключения
            if hasattr(exc, "status_code"):
                status_code = exc.status_code
            else:
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            
            # Формируем ответ
            return JSONResponse(
                status_code=status_code,
                content={
                    "error": exc.__class__.__name__,
                    "detail": str(exc),
                    "request_id": request_context.get().get("request_id", "unknown")
                }
            )

def setup_logging(app: FastAPI):
    """
    Настройка логирования и обработки исключений
    """
    # Добавляем middleware для контекста запроса
    app.add_middleware(RequestContextMiddleware)
    
    # Добавляем глобальный обработчик исключений
    GlobalExceptionHandler(app)
    
    # Настраиваем базовое логирование
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s',  # Используем простой формат, так как форматирование делает StructuredLogger
        handlers=[
            logging.StreamHandler(),  # Вывод в консоль
        ]
    )
    
    # Возвращаем фабричную функцию для создания логгеров
    return get_logger
