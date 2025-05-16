from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
import os

# Changed to absolute imports assuming admin.py is in routers/ and other modules are at the same level as routers/
from models import Tenant, FAQ # Specific models imported
from deps import get_db
from schemas import admin as admin_schemas

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
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
async def create_tenant(tenant_data: admin_schemas.TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant."""
    db_tenant = db.query(Tenant).filter(Tenant.phone_id == tenant_data.phone_id).first()
    if db_tenant:
        raise HTTPException(status_code=400, detail=f"Tenant with phone_id {tenant_data.phone_id} already exists.")
    
    new_tenant = Tenant(**tenant_data.model_dump())
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    return new_tenant

@router.get("/tenants/", response_model=list[admin_schemas.TenantResponse], dependencies=[Depends(verify_admin_token)])
async def list_tenants(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all tenants."""
    tenants = db.query(Tenant).offset(skip).limit(limit).all()
    return tenants

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
    return db_tenant

@router.delete("/tenants/{tenant_id}", status_code=204, dependencies=[Depends(verify_admin_token)])
async def delete_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Delete a tenant."""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    db.delete(db_tenant)
    db.commit()
    return

# === FAQ Management ===

@router.post("/tenants/{tenant_id}/faq/", response_model=admin_schemas.FAQResponse, dependencies=[Depends(verify_admin_token)])
async def create_faq_entry(tenant_id: str, faq_data: admin_schemas.FAQCreate, db: Session = Depends(get_db)):
    """Create a new FAQ entry for a tenant."""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")

    new_faq = FAQ(**faq_data.model_dump(), tenant_id=tenant_id)
    db.add(new_faq)
    db.commit()
    db.refresh(new_faq)
    return new_faq

@router.get("/tenants/{tenant_id}/faq/", response_model=list[admin_schemas.FAQResponse], dependencies=[Depends(verify_admin_token)])
async def list_faq_entries(tenant_id: str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all FAQ entries for a tenant."""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")

    faqs = db.query(FAQ).filter(FAQ.tenant_id == tenant_id).offset(skip).limit(limit).all()
    return faqs

@router.get("/tenants/{tenant_id}/faq/{faq_id}", response_model=admin_schemas.FAQResponse, dependencies=[Depends(verify_admin_token)])
async def get_faq_entry(tenant_id: str, faq_id: int, db: Session = Depends(get_db)):
    """Get a specific FAQ entry."""
    faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail=f"FAQ entry with id {faq_id} for tenant {tenant_id} not found.")
    return faq

@router.put("/tenants/{tenant_id}/faq/{faq_id}", response_model=admin_schemas.FAQResponse, dependencies=[Depends(verify_admin_token)])
async def update_faq_entry(tenant_id: str, faq_id: int, faq_update: admin_schemas.FAQUpdate, db: Session = Depends(get_db)):
    """Update an existing FAQ entry."""
    db_faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
    if not db_faq:
        raise HTTPException(status_code=404, detail=f"FAQ entry with id {faq_id} for tenant {tenant_id} not found.")

    update_data = faq_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_faq, key, value)
    
    db.commit()
    db.refresh(db_faq)
    return db_faq

@router.delete("/tenants/{tenant_id}/faq/{faq_id}", status_code=204, dependencies=[Depends(verify_admin_token)])
async def delete_faq_entry(tenant_id: str, faq_id: int, db: Session = Depends(get_db)):
    """Delete an FAQ entry."""
    db_faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
    if not db_faq:
        raise HTTPException(status_code=404, detail=f"FAQ entry with id {faq_id} for tenant {tenant_id} not found.")
    
    db.delete(db_faq)
    db.commit()
    return
