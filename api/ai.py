# api/ai.py
import logging
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from sqlalchemy import text

from .models import FAQ  # Assuming FAQ model is in models.py

# Configure logging
logger = logging.getLogger(__name__)

# --- Configuration --- #
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
MODEL = None
EMBEDDING_DIM = 0

def load_embedding_model():
    global MODEL, EMBEDDING_DIM
    if MODEL is None:
        try:
            logger.info(f"Loading sentence transformer model: {EMBEDDING_MODEL_NAME}")
            MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
            EMBEDDING_DIM = MODEL.get_sentence_embedding_dimension()
            logger.info(f"Sentence transformer model loaded. Embedding dimension: {EMBEDDING_DIM}")
        except Exception as e:
            logger.error(f"Error loading sentence transformer model: {e}", exc_info=True)
            MODEL = None
            EMBEDDING_DIM = 384  # Fallback for 'all-MiniLM-L6-v2'

# Load the model at startup (when this module is imported)
load_embedding_model()

# --- Embedding Generation --- #
def generate_embedding(text_content: str) -> list[float] | None:
    """
    Generates a vector embedding for the given text content.
    """
    if MODEL is None:
        logger.error("Sentence embedding model is not loaded. Cannot generate embedding.")
        # Attempt to reload the model if it failed initially
        load_embedding_model()
        if MODEL is None:
             raise RuntimeError("Sentence embedding model could not be loaded.")

    if not text_content or not isinstance(text_content, str):
        logger.warning("Invalid or empty text_content provided for embedding generation.")
        return None
    
    try:
        embedding = MODEL.encode(text_content, convert_to_tensor=False) # Returns a numpy array
        return embedding.tolist() # Convert to list for easier storage/JSON serialization
    except Exception as e:
        logger.error(f"Error during embedding generation for text: '{text_content[:50]}...': {e}", exc_info=True)
        return None

# --- Database Interaction with pgvector --- #
async def find_relevant_faqs(db: Session, tenant_id: str, user_query: str, top_k: int = 3) -> list[FAQ]:
    """
    Finds the top_k most relevant FAQs from the database for a specific tenant
    based on the user query, using cosine similarity with pgvector.
    """
    if MODEL is None:
        logger.error("Sentence embedding model is not loaded. Cannot find relevant FAQs.")
        raise RuntimeError("Sentence embedding model is not loaded.")

    if not user_query:
        logger.warning("Empty user query provided.")
        return []

    query_embedding = generate_embedding(user_query)
    if query_embedding is None:
        logger.warning(f"Could not generate embedding for query: {user_query}")
        return []

    try:
        # Using SQLAlchemy's ORM with pgvector's l2_distance or cosine_distance
        # FAQ.embedding.cosine_distance(query_embedding) for cosine distance (lower is better)
        # FAQ.embedding.l2_distance(query_embedding) for L2 distance (lower is better)
        # pgvector recommends using inner_product (<#>) for normalized embeddings for maximum inner product search (MIPS)
        # which is equivalent to cosine similarity if embeddings are normalized.
        # SentenceTransformer models like 'all-MiniLM-L6-v2' produce normalized embeddings.
        # So, we can use inner product and order by descending (higher is better).
        # Or use cosine_distance and order by ascending (lower is better).
        
        # Let's use cosine_distance as it's more intuitive (0 = identical, 2 = opposite)
        relevant_faqs = (
            db.query(FAQ)
            .filter(FAQ.tenant_id == tenant_id)
            .filter(FAQ.embedding != None) # Ensure embedding is not null
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
    # The actual system_prompt for the tenant should be fetched and used here.
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
    # Ensure your DATABASE_URL is set if you plan to test DB interactions.
    
    print(f"Embedding model name: {EMBEDDING_MODEL_NAME}")
    print(f"Embedding dimension: {EMBEDDING_DIM}")

    sample_text = "What is pgvector?"
    embedding = generate_embedding(sample_text)
    if embedding:
        print(f"\nEmbedding for '{sample_text}':\n{embedding[:5]}... (first 5 dimensions)")
        print(f"Length of embedding: {len(embedding)}")
    else:
        print(f"Could not generate embedding for '{sample_text}'.")

    # To test find_relevant_faqs and get_rag_response, you'd need to set up
    # a SQLAlchemy session and have some data in your database.
    # Example (very basic, adapt as needed):
    # from sqlalchemy import create_engine
    # from sqlalchemy.orm import sessionmaker
    # from your_project.config import settings # Assuming you have DATABASE_URL in settings

    # DATABASE_URL = "postgresql://user:password@host:port/database"
    # engine = create_engine(DATABASE_URL)
    # SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # db_session = SessionLocal()
    # try:
    #     async def main_test():
    #         test_query = "How do I reset my password?"
    #         tenant = "some_tenant_id_from_db"
    #         system_p = "You are a helpful bot."
    #         # Add some dummy FAQs with embeddings to your DB first for this to work
    #         response = await get_rag_response(db_session, tenant, test_query, system_p)
    #         print(f"\n--- Test RAG Response for '{test_query}' ---\n{response}")
    #     import asyncio
    #     asyncio.run(main_test())
    # finally:
    #     db_session.close()
    pass
