from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# === Tenant Schemas ===

class TenantBase(BaseModel):
    phone_id: str = Field(..., description="WhatsApp Phone Number ID for the tenant")
    wh_token: str = Field(..., description="WhatsApp Permanent Token for the tenant")
    system_prompt: Optional[str] = Field("You are a helpful assistant.", description="Default system prompt for the AI")

class TenantCreate(TenantBase):
    id: str = Field(..., description="Unique identifier for the tenant (e.g., a slug or UUID)")

class TenantUpdate(BaseModel):
    phone_id: Optional[str] = None
    wh_token: Optional[str] = None
    system_prompt: Optional[str] = None

class TenantResponse(TenantBase):
    id: str

    class Config:
        from_attributes = True # Changed from orm_mode for Pydantic v2

# === FAQ Schemas ===

class FAQBase(BaseModel):
    question: str = Field(..., description="The question part of the FAQ")
    answer: str = Field(..., description="The answer part of the FAQ")

class FAQCreate(FAQBase):
    pass

class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    # embedding: Optional[List[float]] = None # If embedding updates are handled via API

class FAQResponse(FAQBase):
    id: int
    tenant_id: str
    # embedding: Optional[List[float]] = None # Decide if embedding should be in response
    ts: Optional[datetime] = None # Assuming 'ts' is part of your FAQ model

    class Config:
        from_attributes = True # Changed from orm_mode for Pydantic v2

