# api/ai.py

# Import necessary libraries
# For generating embeddings
from sentence_transformers import SentenceTransformer

# For interacting with PostgreSQL and pgvector
from sqlalchemy.orm import Session
from sqlalchemy import text, create_engine # We'll need create_engine if we manage connections here
from pgvector.sqlalchemy import Vector

# Potentially your database models if they are relevant here (e.g., FAQ model)
# from .models import FAQ # Assuming FAQ model is in models.py and has an embedding column

# For OpenAI or other LLM interactions (if this file handles generation)
# import openai
# from your_project.config import settings # If you have a config file for API keys

# --- Configuration --- 
# It's good practice to load configurations like model names or database URLs from environment variables or a config file
# For now, we can define some placeholders or defaults.

# Initialize the sentence transformer model
# We'll use a pre-trained model. A common choice is 'all-MiniLM-L6-v2' for good balance of speed and quality.
# This model will be downloaded the first time it's used if not already cached.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
# It's better to initialize the model once and reuse it.
# We can do this globally or within a class/function that gets called once.
# For simplicity in a script, a global instance is okay, but for a web app, consider managing its lifecycle.
try:
    MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
    EMBEDDING_DIM = MODEL.get_sentence_embedding_dimension()
except Exception as e:
    print(f"Error loading sentence transformer model: {e}")
    MODEL = None
    EMBEDDING_DIM = 384 # Default for 'all-MiniLM-L6-v2', set a fallback

# --- Embedding Generation --- 
def generate_embedding(text_content: str):
    """
    Generates a vector embedding for the given text content.
    """
    if MODEL is None:
        raise RuntimeError("Sentence embedding model is not loaded.")
    if not text_content or not isinstance(text_content, str):
        # Handle empty or invalid input if necessary, or let the model handle it
        return None 
    
    embedding = MODEL.encode(text_content, convert_to_tensor=False) # Returns a numpy array
    return embedding.tolist() # Convert to list for easier storage/JSON serialization if needed

# --- Database Interaction with pgvector --- 
# These functions will interact with your FAQ table, which needs an embedding column of type Vector.
# We'll assume you have a SQLAlchemy session (db: Session) passed from your API routes.

async def add_faq_embedding_to_db(db: Session, faq_id: int, question: str, answer: str):
    """
    Generates embedding for a new FAQ entry (e.g., from question or question+answer)
    and stores it in the database. This function would typically be called when a new FAQ is created/updated.
    
    NOTE: This is a conceptual function. The actual update to the FAQ model
    to include an embedding column and the pgvector type needs to be done in `models.py`
    and a new Alembic migration created and applied (part of Task 11).
    """
    # For RAG, you might want to embed the question, the answer, or a combination.
    # Let's assume we embed the question for retrieval for now.
    content_to_embed = f"Question: {question} Answer: {answer}" # Or just question
    embedding = generate_embedding(content_to_embed)
    
    if embedding is None:
        print(f"Could not generate embedding for FAQ ID {faq_id}")
        return

    # This is where you would update your FAQ table.
    # Example (pseudo-code, actual implementation depends on your FAQ model and session management):
    # faq_item = db.query(FAQ).filter(FAQ.id == faq_id).first()
    # if faq_item:
    #     faq_item.embedding = embedding # Assuming 'embedding' is a Vector column in your FAQ model
    #     db.commit()
    # else:
    #     print(f"FAQ item with ID {faq_id} not found.")
    print(f"Conceptual: Embedding for FAQ ID {faq_id} would be added here. Actual DB update requires model changes and migration.")
    # For now, we'll just print. The actual DB update is part of Task 11 (migrating to Postgres + pgvector)
    # and requires changes to your models.py and a new Alembic migration.
    return embedding # Return for potential immediate use or testing

async def find_relevant_faqs(db: Session, user_query: str, top_k: int = 3):
    """
    Finds the top_k most relevant FAQs from the database based on the user query.
    Uses cosine similarity with pgvector.
    
    NOTE: This also depends on the FAQ model having an 'embedding' column of type Vector
    and pgvector being enabled in your PostgreSQL database (Task 11).
    """
    if not user_query:
        return []

    query_embedding = generate_embedding(user_query)
    if query_embedding is None:
        return []

    # Example SQL query using pgvector's cosine distance operator (<->)
    # This assumes your table is 'faqs' and has an 'embedding' column.
    # The actual table and column names would come from your SQLAlchemy model (e.g., FAQ.embedding)
    
    # IMPORTANT: The following is a raw SQL example. With SQLAlchemy and pgvector, 
    # you can often use model attributes directly in queries if the pgvector extension for SQLAlchemy is set up.
    # from pgvector.sqlalchemy import Vector
    # results = db.query(FAQ).order_by(FAQ.embedding.cosine_distance(query_embedding)).limit(top_k).all()
    
    # For now, let's represent the conceptual query:
    # stmt = text(f"""
    #     SELECT id, question, answer, embedding <-> CAST(:query_embedding AS vector) AS distance
    #     FROM faqs
    #     ORDER BY distance
    #     LIMIT :top_k
    # """)
    # results = db.execute(stmt, {"query_embedding": str(query_embedding), "top_k": top_k}).fetchall()
    
    print(f"Conceptual: Would search for FAQs relevant to '{user_query}' using its embedding.")
    print("Actual implementation requires pgvector setup in DB and model changes (Task 11).")
    # Placeholder result
    # return [{"id": r.id, "question": r.question, "answer": r.answer, "distance": r.distance} for r in results]
    return [] # Placeholder until DB integration is complete

# --- RAG Core Logic --- 
async def get_rag_response(db: Session, user_query: str, tenant_id: str):
    """
    Core RAG function:
    1. Finds relevant FAQs for the user_query and tenant_id.
    2. Constructs a prompt with this context.
    3. Sends the prompt to an LLM (e.g., OpenAI) to generate a response.
    """
    print(f"RAG: Received query '{user_query}' for tenant '{tenant_id}'")
    
    # Step 1: Find relevant FAQs
    # Note: You'll need to adapt find_relevant_faqs to also filter by tenant_id
    # This might mean your FAQ table needs a tenant_id column and the query should include it.
    # For now, find_relevant_faqs is a general placeholder.
    relevant_faqs = await find_relevant_faqs(db, user_query, top_k=3)
    
    if not relevant_faqs:
        # Fallback: if no relevant FAQs found, maybe just use the LLM directly or return a default message.
        # For now, let's try to generate a response without specific context.
        context_str = "No specific information found in the knowledge base."
    else:
        context_str = "\n\nRelevant information from knowledge base:\n"
        for i, faq in enumerate(relevant_faqs):
            # Assuming faq is a dict or object with 'question' and 'answer' keys/attributes
            context_str += f"{i+1}. Question: {faq.get('question', 'N/A')}\n   Answer: {faq.get('answer', 'N/A')}\n"

    # Step 2: Construct the prompt
    # You'll need the system prompt for the tenant, which you might fetch from the DB or have available.
    # For now, using a generic system prompt.
    # system_prompt = fetch_tenant_system_prompt(db, tenant_id) # You'd need this function
    system_prompt = "You are a helpful assistant. Please answer the user's question based on the provided context if available."
    
    prompt = f"{system_prompt}\n\nContext:\n{context_str}\n\nUser Question: {user_query}\n\nAnswer:"
    
    print(f"\n--- Prompt for LLM ---\n{prompt}\n-----------------------")

    # Step 3: Send to LLM (e.g., OpenAI)
    # This part requires an LLM client, like the OpenAI Python library, and an API key.
    # Example (conceptual, replace with actual OpenAI call):
    # try:
    #     openai.api_key = settings.OPENAI_API_KEY # From your config
    #     response = openai.ChatCompletion.create(
    #         model="gpt-3.5-turbo", # Or your preferred model
    #         messages=[
    #             {"role": "system", "content": system_prompt},
    #             {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {user_query}"}
    #         ]
    #     )
    #     llm_answer = response.choices[0].message.content.strip()
    # except Exception as e:
    #     print(f"Error calling LLM: {e}")
    #     llm_answer = "I encountered an error trying to generate a response."
    
    llm_answer = f"(Conceptual LLM Response) Based on the query '{user_query}' and context, this is the answer."
    print(f"RAG: Generated conceptual LLM answer: {llm_answer}")
    
    return llm_answer

# Example usage (for testing purposes, not for direct use in FastAPI app without async handling)
if __name__ == "__main__":
    # This block is for local testing of the functions if you run `python api/ai.py`
    # It won't work as is without a database session and proper async setup.
    
    print(f"Embedding model loaded. Embedding dimension: {EMBEDDING_DIM}")
    
    sample_text = "What is pgvector?"
    embedding = generate_embedding(sample_text)
    print(f"\nEmbedding for '{sample_text}':\n{embedding[:5]}... (first 5 dimensions)")
    print(f"Length of embedding: {len(embedding) if embedding else 'N/A'}")

    # Conceptual test of RAG flow (without actual DB or LLM calls)
    class MockDBSession:
        def query(self, *args, **kwargs): return self # Mocking
        def filter(self, *args, **kwargs): return self
        def order_by(self, *args, **kwargs): return self
        def limit(self, *args, **kwargs): return self
        def all(self): return [] # Mock to return no FAQs
        def execute(self, *args, **kwargs): return self
        def fetchall(self): return []

    mock_db = MockDBSession()
    
    async def main_test():
        test_query = "How do I reset my password?"
        tenant = "test_tenant"
        response = await get_rag_response(mock_db, test_query, tenant)
        print(f"\n--- Test RAG Response for '{test_query}' ---\n{response}")

    import asyncio
    asyncio.run(main_test())


