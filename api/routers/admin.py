from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
import os

# Assuming your models and database session setup are in these locations
# Adjust imports as per your project structure
from .. import models, deps # Placeholder, adjust to your project structure for models and get_db
from ..schemas import admin as admin_schemas # Placeholder for Pydantic schemas

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    # dependencies=[Depends(verify_admin_token)], # Optional: common dependency for all admin routes
)

# --- Admin Token Verification Dependency ---
def verify_admin_token(x_admin_token: str = Header(None)):
    """Dependency to verify the admin token."""
    expected_token = os.getenv("X_ADMIN_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=500, detail="Admin token not configured on server.")
    if not x_admin_token or x_admin_token != expected_token:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Admin-Token.")
    return True

# === Tenant Management ===

@router.post("/tenants/", response_model=admin_schemas.TenantResponse, dependencies=[Depends(verify_admin_token)])
async def create_tenant(tenant_data: admin_schemas.TenantCreate, db: Session = Depends(deps.get_db)):
    """Create a new tenant."""
    # Check if tenant with phone_id already exists
    db_tenant = db.query(models.Tenant).filter(models.Tenant.phone_id == tenant_data.phone_id).first()
    if db_tenant:
        raise HTTPException(status_code=400, detail=f"Tenant with phone_id {tenant_data.phone_id} already exists.")
    
    # Add more robust ID generation if needed, or let DB handle it if autoincrement/default
    new_tenant = models.Tenant(**tenant_data.model_dump())
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    return new_tenant

@router.get("/tenants/", response_model=list[admin_schemas.TenantResponse], dependencies=[Depends(verify_admin_token)])
async def list_tenants(skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    """List all tenants."""
    tenants = db.query(models.Tenant).offset(skip).limit(limit).all()
    return tenants

@router.get("/tenants/{tenant_id}", response_model=admin_schemas.TenantResponse, dependencies=[Depends(verify_admin_token)])
async def get_tenant(tenant_id: str, db: Session = Depends(deps.get_db)):
    """Get a specific tenant by ID."""
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    return tenant

@router.put("/tenants/{tenant_id}", response_model=admin_schemas.TenantResponse, dependencies=[Depends(verify_admin_token)])
async def update_tenant(tenant_id: str, tenant_update: admin_schemas.TenantUpdate, db: Session = Depends(deps.get_db)):
    """Update an existing tenant."""
    db_tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    update_data = tenant_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_tenant, key, value)
    
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@router.delete("/tenants/{tenant_id}", status_code=204, dependencies=[Depends(verify_admin_token)])
async def delete_tenant(tenant_id: str, db: Session = Depends(deps.get_db)):
    """Delete a tenant."""
    db_tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    # Consider cascading deletes or handling related messages/FAQ entries if necessary
    db.delete(db_tenant)
    db.commit()
    return

# === FAQ Management ===

@router.post("/tenants/{tenant_id}/faq/", response_model=admin_schemas.FAQResponse, dependencies=[Depends(verify_admin_token)])
async def create_faq_entry(tenant_id: str, faq_data: admin_schemas.FAQCreate, db: Session = Depends(deps.get_db)):
    """Create a new FAQ entry for a tenant."""
    # Verify tenant exists
    db_tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")

    # Add RAG embedding logic here when creating FAQ if applicable
    # For now, just saving question and answer
    new_faq = models.FAQ(**faq_data.model_dump(), tenant_id=tenant_id)
    # If your FAQ model has an embedding field, you'd populate it here, e.g.:
    # new_faq.embedding = generate_embedding(faq_data.question + " " + faq_data.answer) # Placeholder
    db.add(new_faq)
    db.commit()
    db.refresh(new_faq)
    return new_faq

@router.get("/tenants/{tenant_id}/faq/", response_model=list[admin_schemas.FAQResponse], dependencies=[Depends(verify_admin_token)])
async def list_faq_entries(tenant_id: str, skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    """List all FAQ entries for a tenant."""
    # Verify tenant exists
    db_tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")

    faqs = db.query(models.FAQ).filter(models.FAQ.tenant_id == tenant_id).offset(skip).limit(limit).all()
    return faqs

@router.get("/tenants/{tenant_id}/faq/{faq_id}", response_model=admin_schemas.FAQResponse, dependencies=[Depends(verify_admin_token)])
async def get_faq_entry(tenant_id: str, faq_id: int, db: Session = Depends(deps.get_db)):
    """Get a specific FAQ entry."""
    faq = db.query(models.FAQ).filter(models.FAQ.id == faq_id, models.FAQ.tenant_id == tenant_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail=f"FAQ entry with id {faq_id} for tenant {tenant_id} not found.")
    return faq

@router.put("/tenants/{tenant_id}/faq/{faq_id}", response_model=admin_schemas.FAQResponse, dependencies=[Depends(verify_admin_token)])
async def update_faq_entry(tenant_id: str, faq_id: int, faq_update: admin_schemas.FAQUpdate, db: Session = Depends(deps.get_db)):
    """Update an existing FAQ entry."""
    db_faq = db.query(models.FAQ).filter(models.FAQ.id == faq_id, models.FAQ.tenant_id == tenant_id).first()
    if not db_faq:
        raise HTTPException(status_code=404, detail=f"FAQ entry with id {faq_id} for tenant {tenant_id} not found.")

    update_data = faq_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_faq, key, value)
    
    # If question/answer changes, embedding might need to be updated
    # if "question" in update_data or "answer" in update_data:
    #     db_faq.embedding = generate_embedding(db_faq.question + " " + db_faq.answer) # Placeholder

    db.commit()
    db.refresh(db_faq)
    return db_faq

@router.delete("/tenants/{tenant_id}/faq/{faq_id}", status_code=204, dependencies=[Depends(verify_admin_token)])
async def delete_faq_entry(tenant_id: str, faq_id: int, db: Session = Depends(deps.get_db)):
    """Delete an FAQ entry."""
    db_faq = db.query(models.FAQ).filter(models.FAQ.id == faq_id, models.FAQ.tenant_id == tenant_id).first()
    if not db_faq:
        raise HTTPException(status_code=404, detail=f"FAQ entry with id {faq_id} for tenant {tenant_id} not found.")
    
    db.delete(db_faq)
    db.commit()
    return

# Placeholder for embedding generation - to be implemented with RAG logic
# def generate_embedding(text: str) -> list[float]:
#     # Replace with actual embedding model call (e.g., OpenAI, Sentence Transformers)
#     print(f"[INFO] Generating embedding for text (stub): {text[:50]}...")
#     return [0.1] * 128 # Example dimension

