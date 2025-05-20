# api/routers/admin.py с структурированным логированием
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import os
import math
from datetime import datetime   
from typing import Optional, List

# Changed to absolute imports assuming admin.py is in routers/ and other modules are at the same level as routers/
from models import Tenant, FAQ, Message # Added Message model import
from deps import get_db
from schemas import admin as admin_schemas
from schemas.bulk_import import BulkFAQImportRequest, BulkFAQImportResponse
from ai import generate_embedding # Import for generating embeddings
from logging_utils import get_logger
from tasks import process_bulk_faq_import

# Инициализируем структурированный логгер
logger = get_logger(__name__)

# Log the expected token at module load time for initial check
EXPECTED_ADMIN_TOKEN_ON_LOAD = os.getenv("X_ADMIN_TOKEN")
logger.info("Admin module loaded", extra={
    "expected_token_length": len(EXPECTED_ADMIN_TOKEN_ON_LOAD) if EXPECTED_ADMIN_TOKEN_ON_LOAD else 0
})

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)

# --- Admin Token Verification Dependency ---
def verify_admin_token(x_admin_token: str = Header(None)):
    """Dependency to verify the admin token."""
    expected_token = os.getenv("X_ADMIN_TOKEN")
    logger.info("Verifying admin token", extra={
        "expected_token_exists": bool(expected_token),
        "received_token_exists": bool(x_admin_token)
    })

    if not expected_token:
        logger.error("Admin token not configured on server")
        raise HTTPException(status_code=500, detail="Admin token not configured on server.")
    
    if not x_admin_token:
        logger.warning("Missing X-Admin-Token header")
        raise HTTPException(status_code=403, detail="Missing X-Admin-Token header.")

    if x_admin_token != expected_token:
        logger.warning("Invalid admin token provided", extra={
            "token_match": False
        })
        raise HTTPException(status_code=403, detail="Invalid X-Admin-Token.")
    
    logger.info("Admin token verification successful")
    return True

# === Tenant Management ===

@router.post("/tenants/", response_model=admin_schemas.TenantResponse, dependencies=[Depends(verify_admin_token)])
async def create_tenant(tenant_data: admin_schemas.TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant."""
    db_tenant = db.query(Tenant).filter(Tenant.phone_id == tenant_data.phone_id).first()
    if db_tenant:
        raise HTTPException(status_code=400, detail=f"Tenant with phone_id {tenant_data.phone_id} already exists.")
    
    new_tenant = Tenant(**tenant_data.model_dump())
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    logger.info("Tenant created", extra={
        "tenant_id": new_tenant.id,
        "phone_id": new_tenant.phone_id
    })
    return new_tenant

@router.get("/tenants/", response_model=admin_schemas.PaginatedResponse[admin_schemas.TenantResponse], dependencies=[Depends(verify_admin_token)])
async def list_tenants(
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    phone_id: Optional[str] = None,
    system_prompt_contains: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all tenants with pagination and filtering.
    
    - **phone_id**: Filter by exact phone_id match
    - **system_prompt_contains**: Filter by system_prompt containing this text
    """
    # Build query with filters
    query = db.query(Tenant)
    
    # Apply filters if provided
    if phone_id:
        query = query.filter(Tenant.phone_id == phone_id)
    if system_prompt_contains:
        query = query.filter(Tenant.system_prompt.ilike(f"%{system_prompt_contains}%"))
    
    # Calculate total count with filters applied
    total = query.count()
    
    # Calculate pagination values
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    skip = (page - 1) * page_size
    
    # Get items for current page
    tenants = query.offset(skip).limit(page_size).all()
    
    logger.info("Tenants list retrieved", extra={
        "total": total,
        "page": page,
        "page_size": page_size,
        "filters": {
            "phone_id": phone_id,
            "system_prompt_contains": system_prompt_contains
        }
    })
    
    # Create paginated response
    return {
        "items": tenants,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

@router.get("/tenants/{tenant_id}", response_model=admin_schemas.TenantResponse, dependencies=[Depends(verify_admin_token)])
async def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Get a specific tenant by ID."""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        logger.warning("Tenant not found", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    logger.info("Tenant retrieved", extra={"tenant_id": tenant_id})
    return tenant

@router.put("/tenants/{tenant_id}", response_model=admin_schemas.TenantResponse, dependencies=[Depends(verify_admin_token)])
async def update_tenant(tenant_id: str, tenant_update: admin_schemas.TenantUpdate, db: Session = Depends(get_db)):
    """Update an existing tenant."""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        logger.warning("Tenant not found for update", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    update_data = tenant_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_tenant, key, value)
    
    db.commit()
    db.refresh(db_tenant)
    logger.info("Tenant updated", extra={
        "tenant_id": tenant_id,
        "updated_fields": list(update_data.keys())
    })
    return db_tenant

@router.delete("/tenants/{tenant_id}", status_code=204, dependencies=[Depends(verify_admin_token)])
async def delete_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Delete a tenant."""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        logger.warning("Tenant not found for deletion", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    db.delete(db_tenant)
    db.commit()
    logger.info("Tenant deleted", extra={"tenant_id": tenant_id})
    return

# === FAQ Management ===

@router.post("/tenants/{tenant_id}/faq/", response_model=admin_schemas.FAQResponse, dependencies=[Depends(verify_admin_token)])
async def create_faq_entry(tenant_id: str, faq_data: admin_schemas.FAQCreate, db: Session = Depends(get_db)):
    """Create a new FAQ entry for a tenant and generate its embedding."""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        logger.warning("Tenant not found for FAQ creation", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")

    content_to_embed = f"Question: {faq_data.question} Answer: {faq_data.answer}"
    embedding = await generate_embedding(content_to_embed)
    if embedding is None:
        logger.error("Failed to generate embedding for FAQ", extra={
            "tenant_id": tenant_id,
            "question_preview": faq_data.question[:50] + "..." if len(faq_data.question) > 50 else faq_data.question
        })
        raise HTTPException(status_code=500, detail="Failed to generate embedding for FAQ content.")

    new_faq = FAQ(**faq_data.model_dump(), tenant_id=tenant_id, embedding=embedding)
    db.add(new_faq)
    db.commit()
    db.refresh(new_faq)
    logger.info("FAQ entry created", extra={
        "faq_id": new_faq.id,
        "tenant_id": tenant_id,
        "question_length": len(faq_data.question),
        "answer_length": len(faq_data.answer)
    })
    return new_faq

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
        logger.warning("Tenant not found for bulk FAQ import", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    # Преобразуем Pydantic модели в словари для сериализации
    import_items = [item.model_dump() for item in import_data.items]
    
    # Запускаем Celery-задачу
    task = process_bulk_faq_import.delay(tenant_id=tenant_id, import_items=import_items)
    
    logger.info("Bulk FAQ import task started", extra={
        "tenant_id": tenant_id,
        "items_count": len(import_data.items),
        "task_id": task.id
    })
    
    # Возвращаем ID задачи для отслеживания
    return {
        "total_items": len(import_data.items),
        "successful_items": 0,  # Будет обработано в фоновой задаче
        "failed_items": 0,      # Будет обработано в фоновой задаче
        "errors": None,         # Будет записано в логи
        "task_id": task.id      # ID задачи для отслеживания
    }

# Остальные методы также обновляются аналогичным образом...
