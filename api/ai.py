# api/ai.py
import logging
import os
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from models import FAQ  # Assuming FAQ model is in models.py

# Configure logging
logger = logging.getLogger(__name__)

# --- Configuration --- #
EMBEDDING_MODEL_NAME = "text-embedding-ada-002"  # OpenAI model with 1536 dimensions
EMBEDDING_DIM = 1536  # Fixed dimension for OpenAI text-embedding-ada-002
client = None

def load_embedding_model():
    global client
    if client is None:
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY environment variable not set")
                raise ValueError("OPENAI_API_KEY environment variable not set")
            
            logger.info(f"Initializing OpenAI client for embeddings model: {EMBEDDING_MODEL_NAME}")
            client = AsyncOpenAI(api_key=api_key)
            logger.info(f"OpenAI client initialized. Embedding dimension: {EMBEDDING_DIM}")
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {e}", exc_info=True)
            client = None

# Load the client at startup (when this module is imported)
load_embedding_model()

# --- Embedding Generation --- #
async def generate_embedding(text_content: str) -> list[float] | None:
    """
    Generates a vector embedding for the given text content using OpenAI API.
    """
    global client
    if client is None:
        logger.error("OpenAI client is not initialized. Cannot generate embedding.")
        # Attempt to reload the client if it failed initially
        load_embedding_model()
        if client is None:
             raise RuntimeError("OpenAI client could not be initialized.")

    if not text_content or not isinstance(text_content, str):
        logger.warning("Invalid or empty text_content provided for embedding generation.")
        return None
    
    try:
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL_NAME,
            input=text_content
        )
        embedding = response.data[0].embedding
        return embedding  # Already a list, no conversion needed
    except Exception as e:
        logger.error(f"Error during embedding generation for text: '{text_content[:50]}...': {e}", exc_info=True)
        return None

# --- Database Interaction with pgvector --- #
async def find_relevant_faqs(db: Session, tenant_id: str, user_query: str, top_k: int = 3) -> list[FAQ]:
    """
    Finds the top_k most relevant FAQs from the database for a specific tenant
    based on the user query, using cosine similarity with pgvector.
    """
    global client
    if client is None:
        logger.error("OpenAI client is not initialized. Cannot find relevant FAQs.")
        raise RuntimeError("OpenAI client is not initialized.")

    if not user_query:
        logger.warning("Empty user query provided.")
        return []

    query_embedding = await generate_embedding(user_query)
    if query_embedding is None:
        logger.warning(f"Could not generate embedding for query: {user_query}")
        return []

    try:
        # Using SQLAlchemy's ORM with pgvector's cosine_distance
        # Lower cosine_distance means higher similarity
        relevant_faqs = (
            db.query(FAQ)
            .filter(FAQ.tenant_id == tenant_id)
            .filter(FAQ.embedding != None)  # Ensure embedding is not null
            .order_by(FAQ.embedding.cosine_distance(query_embedding))
            .limit(top_k)
            .all()
        )
        logger.info(f"Found {len(relevant_faqs)} relevant FAQs for tenant '{tenant_id}' and query '{user_query}'.")
        return relevant_faqs
    except Exception as e:
        logger.error(f"Error finding relevant FAQs: {e}", exc_info=True)
        return []

# --- RAG Core Logic --- #
async def get_rag_response(db: Session, tenant_id: str, user_query: str, system_prompt: str) -> str:
    """
    Core RAG function:
    1. Finds relevant FAQs for the user_query and tenant_id.
    2. Constructs a prompt with this context.
    3. (Conceptual) Sends the prompt to an LLM to generate a response.
    """
    logger.info(f"RAG: Received query '{user_query}' for tenant '{tenant_id}'")
    
    relevant_faqs = await find_relevant_faqs(db, tenant_id, user_query, top_k=3)
    
    context_parts = []
    if not relevant_faqs:
        context_str = "No specific information found in the knowledge base for your query."
    else:
        for i, faq_item in enumerate(relevant_faqs):
            context_parts.append(f"{i+1}. Question: {faq_item.question}\n   Answer: {faq_item.answer}")
        context_str = "Relevant information from knowledge base:\n" + "\n\n".join(context_parts)

    # Construct the prompt for the LLM
    prompt = f"{system_prompt}\n\nContext from knowledge base:\n{context_str}\n\nUser Question: {user_query}\n\nAnswer:"
    
    logger.debug(f"--- Prompt for LLM ---\n{prompt}\n-----------------------")

    # Step 3: (Conceptual) Send to LLM (e.g., OpenAI)
    # This part would involve calling an actual LLM API.
    # For now, we'll return a placeholder response that includes the context found.
    
    if not relevant_faqs:
        llm_answer = f"I couldn't find specific information in our knowledge base for your question: '{user_query}'. Please try rephrasing or ask something else."
    else:
        llm_answer = f"Based on the information I found regarding '{user_query}':\n\n{context_str}\n\n(This is a conceptual answer. An actual LLM would synthesize this information to directly answer your question.)"
    
    logger.info(f"RAG: Generated conceptual LLM answer for tenant '{tenant_id}'.")
    return llm_answer

# Example usage (for local testing if needed, ensure DB and models are accessible)
if __name__ == "__main__":
    # This block is for local testing. Requires a database session and async setup.
    # Ensure your OPENAI_API_KEY is set if you plan to test.
    
    print(f"Embedding model name: {EMBEDDING_MODEL_NAME}")
    print(f"Embedding dimension: {EMBEDDING_DIM}")

    # To test embedding generation, you'd need to run this in an async context
    # Example:
    # import asyncio
    # async def test_embedding():
    #     sample_text = "What is pgvector?"
    #     embedding = await generate_embedding(sample_text)
    #     if embedding:
    #         print(f"\nEmbedding for '{sample_text}':\n{embedding[:5]}... (first 5 dimensions)")
    #         print(f"Length of embedding: {len(embedding)}")
    #     else:
    #         print(f"Could not generate embedding for '{sample_text}'.")
    # asyncio.run(test_embedding())
    
    # To test find_relevant_faqs and get_rag_response, you'd need to set up
    # a SQLAlchemy session and have some data in your database.
    pass
