"""
Изменения для api/routers/admin.py:
1. Импортировать Celery-задачу
2. Заменить background_tasks.add_task на вызов Celery-задачи
"""

# Добавить в начало файла:
from tasks import process_bulk_faq_import

# Заменить функцию bulk_import_faq:
@router.post("/tenants/{tenant_id}/faq/bulk-import/", response_model=BulkFAQImportResponse, dependencies=[Depends(verify_admin_token)])
async def bulk_import_faq(
    tenant_id: str, 
    import_data: BulkFAQImportRequest,
    db: Session = Depends(get_db)
):
    """
    Bulk import multiple FAQ entries for a tenant using Celery task queue.
    """
    # Verify tenant exists
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    # Преобразуем Pydantic модели в словари для сериализации
    import_items = [item.model_dump() for item in import_data.items]
    
    # Запускаем Celery-задачу
    task = process_bulk_faq_import.delay(tenant_id=tenant_id, import_items=import_items)
    
    # Возвращаем ID задачи для отслеживания
    return {
        "total_items": len(import_data.items),
        "successful_items": 0,  # Будет обработано в фоновой задаче
        "failed_items": 0,      # Будет обработано в фоновой задаче
        "errors": None,         # Будет записано в логи
        "task_id": task.id      # ID задачи для отслеживания
    }

# Удалить функцию process_bulk_faq_import, так как она перенесена в tasks.py
