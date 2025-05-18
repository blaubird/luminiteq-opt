from fastapi import APIRouter, Depends, HTTPException, Header, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import os
import logging
import math
from typing import Optional, List

# Changed to absolute imports assuming admin.py is in routers/ and other modules are at the same level as routers/
from models import Tenant, FAQ, Message # Added Message model import
from deps import get_db
from schemas import admin as admin_schemas
from schemas.bulk_import import BulkFAQImportRequest, BulkFAQImportResponse
from ai import generate_embedding # Import for generating embeddings

logger = logging.getLogger(__name__)

# Log the expected token at module load time for initial check
EXPECTED_ADMIN_TOKEN_ON_LOAD = os.getenv("X_ADMIN_TOKEN")
logger.info(f"ADMIN_PY_LOAD: Expected X_ADMIN_TOKEN from env: |{EXPECTED_ADMIN_TOKEN_ON_LOAD}|")

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)

# --- Admin Token Verification Dependency ---
def verify_admin_token(x_admin_token: str = Header(None)):
    """Dependency to verify the admin token."""
    expected_token = os.getenv("X_ADMIN_TOKEN")
    logger.info(f"VERIFY_ADMIN_TOKEN: Expected token from os.getenv: |{expected_token}|")
    logger.info(f"VERIFY_ADMIN_TOKEN: Received token from X-Admin-Token header: |{x_admin_token}|")

    if not expected_token:
        logger.error("Admin token (X_ADMIN_TOKEN) is not configured on the server (os.getenv returned None or empty).")
        # Log this specific case before raising HTTP 500
        raise HTTPException(status_code=500, detail="Admin token not configured on server.")
    
    if not x_admin_token:
        logger.warning("Failed admin token verification: X-Admin-Token header is missing or empty.")
        raise HTTPException(status_code=403, detail="Missing X-Admin-Token header.")

    if x_admin_token != expected_token:
        logger.warning(f"Failed admin token verification. Provided token in header |{x_admin_token}| does not match expected token from env |{expected_token}|")
        raise HTTPException(status_code=403, detail="Invalid X-Admin-Token.")
    
    logger.info("Admin token verification successful.")
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
    logger.info(f"Tenant created with ID: {new_tenant.id} and phone_id: {new_tenant.phone_id}")
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
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    return tenant

@router.put("/tenants/{tenant_id}", response_model=admin_schemas.TenantResponse, dependencies=[Depends(verify_admin_token)])
async def update_tenant(tenant_id: str, tenant_update: admin_schemas.TenantUpdate, db: Session = Depends(get_db)):
    """Update an existing tenant."""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    update_data = tenant_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_tenant, key, value)
    
    db.commit()
    db.refresh(db_tenant)
    logger.info(f"Tenant with ID: {tenant_id} updated.")
    return db_tenant

@router.delete("/tenants/{tenant_id}", status_code=204, dependencies=[Depends(verify_admin_token)])
async def delete_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Delete a tenant."""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    db.delete(db_tenant)
    db.commit()
    logger.info(f"Tenant with ID: {tenant_id} deleted.")
    return

# === FAQ Management ===

@router.post("/tenants/{tenant_id}/faq/", response_model=admin_schemas.FAQResponse, dependencies=[Depends(verify_admin_token)])
async def create_faq_entry(tenant_id: str, faq_data: admin_schemas.FAQCreate, db: Session = Depends(get_db)):
    """Create a new FAQ entry for a tenant and generate its embedding."""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")

    content_to_embed = f"Question: {faq_data.question} Answer: {faq_data.answer}"
    embedding = await generate_embedding(content_to_embed)  # Добавлен await
    if embedding is None:
        logger.error(f"Failed to generate embedding for FAQ: Q: {faq_data.question[:50]}... A: {faq_data.answer[:50]}...")
        raise HTTPException(status_code=500, detail="Failed to generate embedding for FAQ content.")

    new_faq = FAQ(**faq_data.model_dump(), tenant_id=tenant_id, embedding=embedding)
    db.add(new_faq)
    db.commit()
    db.refresh(new_faq)
    logger.info(f"FAQ entry created with ID: {new_faq.id} for tenant: {tenant_id}")
    return new_faq

@router.post("/tenants/{tenant_id}/faq/bulk-import/", response_model=BulkFAQImportResponse, dependencies=[Depends(verify_admin_token)])
async def bulk_import_faq(
    tenant_id: str, 
    import_data: BulkFAQImportRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Bulk import multiple FAQ entries for a tenant.
    
    This endpoint processes the import in the background to avoid timeouts with large datasets.
    """
    # Verify tenant exists
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    # Start background task for processing
    background_tasks.add_task(
        process_bulk_faq_import,
        tenant_id=tenant_id,
        import_items=import_data.items,
        db_session_factory=lambda: next(get_db())
    )
    
    # Return immediate response
    return {
        "total_items": len(import_data.items),
        "successful_items": 0,  # Will be processed in background
        "failed_items": 0,      # Will be processed in background
        "errors": None          # Will be logged during processing
    }

async def process_bulk_faq_import(tenant_id: str, import_items: List, db_session_factory):
    """Background task to process bulk FAQ import."""
    db = None
    try:
        db = db_session_factory()
        successful_count = 0
        failed_count = 0
        errors = []
        
        for item in import_items:
            try:
                # Generate embedding for the FAQ
                content_to_embed = f"Question: {item.question} Answer: {item.answer}"
                embedding = await generate_embedding(content_to_embed)
                
                if embedding is None:
                    logger.error(f"Failed to generate embedding for FAQ: Q: {item.question[:50]}...")
                    failed_count += 1
                    errors.append({
                        "question": item.question[:50] + "...",
                        "error": "Failed to generate embedding"
                    })
                    continue
                
                # Create new FAQ entry
                new_faq = FAQ(
                    question=item.question,
                    answer=item.answer,
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
                    "question": item.question[:50] + "...",
                    "error": str(e)
                })
        
        logger.info(f"Bulk import completed for tenant {tenant_id}: {successful_count} successful, {failed_count} failed")
        
    except Exception as e:
        logger.error(f"Error in bulk import background task: {str(e)}")
    finally:
        if db:
            db.close()

@router.get("/tenants/{tenant_id}/faq/", response_model=admin_schemas.PaginatedResponse[admin_schemas.FAQResponse], dependencies=[Depends(verify_admin_token)])
async def list_faq_entries(
    tenant_id: str, 
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    question_contains: Optional[str] = None,
    answer_contains: Optional[str] = None,
    search_text: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all FAQ entries for a tenant with pagination and filtering.
    
    - **question_contains**: Filter by question containing this text
    - **answer_contains**: Filter by answer containing this text
    - **search_text**: Full-text search across both question and answer fields
    """
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")

    # Build query with filters
    query = db.query(FAQ).filter(FAQ.tenant_id == tenant_id)
    
    # Apply filters if provided
    if question_contains:
        query = query.filter(FAQ.question.ilike(f"%{question_contains}%"))
    if answer_contains:
        query = query.filter(FAQ.answer.ilike(f"%{answer_contains}%"))
    if search_text:
        # Full-text search across both question and answer
        query = query.filter(
            or_(
                FAQ.question.ilike(f"%{search_text}%"),
                FAQ.answer.ilike(f"%{search_text}%")
            )
        )
    
    # Calculate total count with filters applied
    total = query.count()
    
    # Calculate pagination values
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    skip = (page - 1) * page_size
    
    # Get items for current page
    faqs = query.offset(skip).limit(page_size).all()
    
    # Create paginated response
    return {
        "items": faqs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

# Добавляем алиас для совместимости с запросами, использующими /faqs/ вместо /faq/
@router.get("/tenants/{tenant_id}/faqs/", response_model=admin_schemas.PaginatedResponse[admin_schemas.FAQResponse], dependencies=[Depends(verify_admin_token)])
async def list_faq_entries_alias(
    tenant_id: str, 
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    question_contains: Optional[str] = None,
    answer_contains: Optional[str] = None,
    search_text: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Alias for list_faq_entries to support /faqs/ path."""
    return await list_faq_entries(tenant_id, page, page_size, question_contains, answer_contains, search_text, db)

@router.get("/tenants/{tenant_id}/faq/{faq_id}", response_model=admin_schemas.FAQResponse, dependencies=[Depends(verify_admin_token)])
async def get_faq_entry(tenant_id: str, faq_id: int, db: Session = Depends(get_db)):
    """Get a specific FAQ entry."""
    faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail=f"FAQ entry with id {faq_id} for tenant {tenant_id} not found.")
    return faq

@router.put("/tenants/{tenant_id}/faq/{faq_id}", response_model=admin_schemas.FAQResponse, dependencies=[Depends(verify_admin_token)])
async def update_faq_entry(tenant_id: str, faq_id: int, faq_update: admin_schemas.FAQUpdate, db: Session = Depends(get_db)):
    """Update an existing FAQ entry. If question or answer changes, regenerate embedding."""
    db_faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
    if not db_faq:
        raise HTTPException(status_code=404, detail=f"FAQ entry with id {faq_id} for tenant {tenant_id} not found.")

    update_data = faq_update.model_dump(exclude_unset=True)
    needs_re_embedding = False
    
    for key, value in update_data.items():
        if key in ["question", "answer"] and getattr(db_faq, key) != value:
            needs_re_embedding = True
        setattr(db_faq, key, value)
    
    if needs_re_embedding or not db_faq.embedding: 
        logger.info(f"Regenerating embedding for FAQ ID: {db_faq.id} due to content change or missing embedding.")
        content_to_embed = f"Question: {db_faq.question} Answer: {db_faq.answer}"
        embedding = await generate_embedding(content_to_embed)  # Добавлен await
        if embedding is None:
            logger.error(f"Failed to regenerate embedding for FAQ ID: {db_faq.id}")
            pass 
        else:
            db_faq.embedding = embedding
    
    db.commit()
    db.refresh(db_faq)
    logger.info(f"FAQ entry with ID: {faq_id} for tenant: {tenant_id} updated.")
    return db_faq

@router.delete("/tenants/{tenant_id}/faq/{faq_id}", status_code=204, dependencies=[Depends(verify_admin_token)])
async def delete_faq_entry(tenant_id: str, faq_id: int, db: Session = Depends(get_db)):
    """Delete an FAQ entry."""
    db_faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
    if not db_faq:
        raise HTTPException(status_code=404, detail=f"FAQ entry with id {faq_id} for tenant {tenant_id} not found.")
    
    db.delete(db_faq)
    db.commit()
    logger.info(f"FAQ entry with ID: {faq_id} for tenant: {tenant_id} deleted.")
    return

# === Message Management ===

@router.post("/tenants/{tenant_id}/messages/", response_model=admin_schemas.MessageResponse, dependencies=[Depends(verify_admin_token)])
async def create_message(tenant_id: str, message_data: admin_schemas.MessageCreate, db: Session = Depends(get_db)):
    """Create a new message for a tenant."""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    # Override tenant_id from path parameter to ensure consistency
    message_data_dict = message_data.model_dump()
    message_data_dict["tenant_id"] = tenant_id
    
    new_message = Message(**message_data_dict)
    db.add(new_message)
    db.commit()
    db.refresh(new_message)
    logger.info(f"Message created with ID: {new_message.id} for tenant: {tenant_id}")
    return new_message

@router.get("/tenants/{tenant_id}/messages/", response_model=admin_schemas.PaginatedResponse[admin_schemas.MessageResponse], dependencies=[Depends(verify_admin_token)])
async def list_messages(
    tenant_id: str, 
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    role: Optional[str] = None,
    text_contains: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """
    List all messages for a tenant with pagination and filtering.
    
    - **role**: Filter by message role (user or assistant)
    - **text_contains**: Filter by message text containing this string
    - **from_date**: Filter messages from this date/time (inclusive)
    - **to_date**: Filter messages until this date/time (inclusive)
    """
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")

    # Build query with filters
    query = db.query(Message).filter(Message.tenant_id == tenant_id)
    
    # Apply filters if provided
    if role:
        query = query.filter(Message.role == role)
    if text_contains:
        query = query.filter(Message.text.ilike(f"%{text_contains}%"))
    if from_date:
        query = query.filter(Message.ts >= from_date)
    if to_date:
        query = query.filter(Message.ts <= to_date)
    
    # Calculate total count with filters applied
    total = query.count()
    
    # Calculate pagination values
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    skip = (page - 1) * page_size
    
    # Get items for current page with default ordering by timestamp descending
    messages = query.order_by(Message.ts.desc()).offset(skip).limit(page_size).all()
    
    # Create paginated response
    return {
        "items": messages,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

@router.get("/tenants/{tenant_id}/messages/{message_id}", response_model=admin_schemas.MessageResponse, dependencies=[Depends(verify_admin_token)])
async def get_message(tenant_id: str, message_id: int, db: Session = Depends(get_db)):
    """Get a specific message."""
    message = db.query(Message).filter(Message.id == message_id, Message.tenant_id == tenant_id).first()
    if not message:
        raise HTTPException(status_code=404, detail=f"Message with id {message_id} for tenant {tenant_id} not found.")
    return message

@router.put("/tenants/{tenant_id}/messages/{message_id}", response_model=admin_schemas.MessageResponse, dependencies=[Depends(verify_admin_token)])
async def update_message(tenant_id: str, message_id: int, message_update: admin_schemas.MessageUpdate, db: Session = Depends(get_db)):
    """Update an existing message."""
    db_message = db.query(Message).filter(Message.id == message_id, Message.tenant_id == tenant_id).first()
    if not db_message:
        raise HTTPException(status_code=404, detail=f"Message with id {message_id} for tenant {tenant_id} not found.")
    
    update_data = message_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_message, key, value)
    
    db.commit()
    db.refresh(db_message)
    logger.info(f"Message with ID: {message_id} for tenant: {tenant_id} updated.")
    return db_message

@router.delete("/tenants/{tenant_id}/messages/{message_id}", status_code=204, dependencies=[Depends(verify_admin_token)])
async def delete_message(tenant_id: str, message_id: int, db: Session = Depends(get_db)):
    """Delete a message."""
    db_message = db.query(Message).filter(Message.id == message_id, Message.tenant_id == tenant_id).first()
    if not db_message:
        raise HTTPException(status_code=404, detail=f"Message with id {message_id} for tenant {tenant_id} not found.")
    
    db.delete(db_message)
    db.commit()
    logger.info(f"Message with ID: {message_id} for tenant: {tenant_id} deleted.")
    return
