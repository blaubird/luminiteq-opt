# api/routers/rag.py
import logging
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from deps import get_db
from models import Tenant # To fetch tenant specific data like system_prompt
from ai import get_rag_response, load_embedding_model # Import RAG logic and model loader
from schemas.rag import RAGQueryRequest, RAGResponse # Define these schemas

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
)

# Ensure the embedding model is loaded when this router is initialized
# This is a good place if ai.py's top-level load_embedding_model() isn't sufficient
# or if you want to be explicit about model loading for this router.
# However, ai.py already calls load_embedding_model() at module import.

@router.post("/query/", response_model=RAGResponse)
async def query_rag_system(
    request_data: RAGQueryRequest,
    db: Session = Depends(get_db)
):
    """
    Receives a user query and tenant ID, retrieves relevant context using RAG,
    and returns a generated response.
    """
    logger.info(f"RAG query received for tenant_id: {request_data.tenant_id}, query: '{request_data.query}'") # Corrected f-string

    # 1. Fetch tenant to get system_prompt (or pass it directly if preferred)
    tenant = db.query(Tenant).filter(Tenant.id == request_data.tenant_id).first()
    if not tenant:
        logger.warning(f"Tenant not found: {request_data.tenant_id}")
        raise HTTPException(status_code=404, detail=f"Tenant with id {request_data.tenant_id} not found.")
    
    system_prompt = tenant.system_prompt
    if not system_prompt:
        logger.warning(f"System prompt not set for tenant {request_data.tenant_id}. Using default.")
        system_prompt = "You are a helpful assistant."

    try:
        # 2. Get RAG response
        answer = await get_rag_response(
            db=db,
            tenant_id=request_data.tenant_id,
            user_query=request_data.query,
            system_prompt=system_prompt
        )
        
        logger.info(f"Successfully generated RAG response for tenant {request_data.tenant_id}")
        return RAGResponse(answer=answer, tenant_id=request_data.tenant_id, query=request_data.query)
    
    except RuntimeError as e:
        # This can happen if the embedding model is not loaded
        logger.error(f"RuntimeError during RAG processing: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=str(e)) # Service Unavailable if model is critical
    except Exception as e:
        logger.error(f"Unexpected error during RAG processing for tenant {request_data.tenant_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while processing your request.")

