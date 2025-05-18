from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class BulkFAQImportItem(BaseModel):
    question: str = Field(..., description="The question part of the FAQ")
    answer: str = Field(..., description="The answer part of the FAQ")

class BulkFAQImportRequest(BaseModel):
    items: List[BulkFAQImportItem] = Field(..., description="List of FAQ items to import")

class BulkFAQImportResponse(BaseModel):
    total_items: int = Field(..., description="Total number of items in the request")
    successful_items: int = Field(..., description="Number of successfully imported items")
    failed_items: int = Field(..., description="Number of items that failed to import")
    errors: Optional[List[Dict[str, Any]]] = Field(None, description="List of errors encountered during import")
