from pydantic import BaseModel, Field
from typing import Optional, List, Generic, TypeVar
from datetime import datetime

# === Pagination Schemas ===
T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool

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

# === Message Schemas ===

class MessageBase(BaseModel):
    role: str = Field(..., description="Role of the message sender (user or assistant)")
    text: str = Field(..., description="Content of the message")

class MessageCreate(MessageBase):
    tenant_id: str = Field(..., description="ID of the tenant this message belongs to")
    wa_msg_id: Optional[str] = Field(None, description="WhatsApp message ID (for user messages)")

class MessageUpdate(BaseModel):
    role: Optional[str] = None
    text: Optional[str] = None
    wa_msg_id: Optional[str] = None

class MessageResponse(MessageBase):
    id: int
    tenant_id: str
    wa_msg_id: Optional[str] = None
    ts: datetime

    class Config:
        from_attributes = True
