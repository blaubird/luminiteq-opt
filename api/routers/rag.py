# api/routers/rag.py с структурированным логированием
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from deps import get_db
from models import Tenant # To fetch tenant specific data like system_prompt
from ai import get_rag_response, load_embedding_model # Import RAG logic and model loader
from schemas.rag import RAGQueryRequest, RAGResponse # Define these schemas
from logging_utils import get_logger

# Инициализируем структурированный логгер
logger = get_logger(__name__)

router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
)

@router.post("/query/", response_model=RAGResponse)
async def query_rag_system(
    request_data: RAGQueryRequest,
    db: Session = Depends(get_db)
):
    """
    Receives a user query and tenant ID, retrieves relevant context using RAG,
    and returns a generated response.
    """
    logger.info("RAG query received", extra={
        "tenant_id": request_data.tenant_id,
        "query": request_data.query
    })

    # 1. Fetch tenant to get system_prompt (or pass it directly if preferred)
    tenant = db.query(Tenant).filter(Tenant.id == request_data.tenant_id).first()
    if not tenant:
        logger.warning("Tenant not found", extra={"tenant_id": request_data.tenant_id})
        raise HTTPException(status_code=404, detail=f"Tenant with id {request_data.tenant_id} not found.")
    
    system_prompt = tenant.system_prompt
    if not system_prompt:
        logger.warning("System prompt not set for tenant, using default", extra={
            "tenant_id": request_data.tenant_id
        })
        system_prompt = "You are a helpful assistant."

    try:
        # 2. Get RAG response
        answer = await get_rag_response(
            db=db,
            tenant_id=request_data.tenant_id,
            user_query=request_data.query,
            system_prompt=system_prompt
        )
        
        logger.info("Successfully generated RAG response", extra={
            "tenant_id": request_data.tenant_id,
            "response_length": len(answer) if answer else 0
        })
        return RAGResponse(answer=answer, tenant_id=request_data.tenant_id, query=request_data.query)
    
    except RuntimeError as e:
        # This can happen if the embedding model is not loaded
        logger.error("RuntimeError during RAG processing", extra={
            "tenant_id": request_data.tenant_id,
            "error_type": "RuntimeError"
        }, exc_info=e)
        raise HTTPException(status_code=503, detail=str(e)) # Service Unavailable if model is critical
    except Exception as e:
        logger.error("Unexpected error during RAG processing", extra={
            "tenant_id": request_data.tenant_id,
            "error_type": type(e).__name__
        }, exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred while processing your request.")
