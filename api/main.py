import os
import logging
from fastapi import FastAPI, Depends, Request, BackgroundTasks, HTTPException, Query, Response
from logging.config import fileConfig
from alembic.config import Config
from alembic import command
import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from deps import get_db, tenant_by_phone_id
from models import Message, Tenant # Added Tenant here for clarity, though not strictly necessary if only used in seeding script

# --- Environment Variable Sanitization ---
# Ensure API keys and tokens are stripped of leading/trailing whitespace.
# This is good practice and is retained.
if os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY").strip()
if os.getenv("WH_TOKEN"):
    os.environ["WH_TOKEN"] = os.getenv("WH_TOKEN").strip()
if os.getenv("WH_PHONE_ID"):
    os.environ["WH_PHONE_ID"] = os.getenv("WH_PHONE_ID").strip()
if os.getenv("VERIFY_TOKEN"):
    os.environ["VERIFY_TOKEN"] = os.getenv("VERIFY_TOKEN").strip()

app = FastAPI(
    title="Luminiteq WhatsApp Integration API",
    description="Handles WhatsApp webhooks and processes messages using AI.",
    version="1.0.0"
)

# Initialize OpenAI client
# It's good practice to check if the API key exists and handle appropriately,
# but for this refactor, we'll assume it's set.
ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Logging Configuration ---
# Basic logging is kept. For production, consider structured logging (e.g., python-json-logger)
# and configurable log levels via environment variables.
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

@app.on_event("startup")
def startup_event():
    logger.info("Application startup: running Alembic migrations.")
    try:
        here = os.path.dirname(__file__)
        # Ensure alembic.ini path is correct relative to this file's location
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
        alembic_cfg = Config(cfg_path)
        # Configure logging for Alembic as well, if not already handled by fileConfig
        # fileConfig(alembic_cfg.config_file_name) # This can sometimes conflict with basicConfig
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations completed successfully.")
    except Exception as e:
        logger.error(f"Error during Alembic migrations: {e}", exc_info=True)
        # Depending on severity, you might want to prevent app startup
        # raise RuntimeError("Database migration failed") from e

    # The temporary tenant seeding logic has been removed.
    # This should be handled by a separate seeding script or a one-time setup process.
    # Example: 
    # if os.getenv("RUN_SEEDER", "false").lower() == "true":
    #     from db import SessionLocal
    #     from models import Tenant # Ensure Tenant is imported
    #     logger.info("Running test tenant seeder...")
    #     # ... (seeding logic here, adapted to be callable)
    #     logger.info("Test tenant seeder finished.")

# --- Health Check Endpoint ---
@app.get("/health", tags=["Monitoring"], summary="Perform a Health Check")
async def health_check():
    # Add more sophisticated checks if needed (e.g., database connectivity)
    return {"status": "ok", "message": "Service is healthy"}

# --- Webhook Verification Endpoint ---
# This endpoint is used by WhatsApp to verify the webhook.
@app.get("/webhook", tags=["Webhook"], summary="Verify WhatsApp Webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode", description="The mode of the verification request (should be 'subscribe')."),
    hub_token: str = Query(..., alias="hub.verify_token", description="The verification token."),
    hub_challenge: str = Query(..., alias="hub.challenge", description="A challenge string to be echoed back."),
):
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
    if not VERIFY_TOKEN:
        logger.error("VERIFY_TOKEN environment variable not set.")
        raise HTTPException(status_code=500, detail="Webhook verification token not configured.")

    if hub_mode == "subscribe" and hub_token == VERIFY_TOKEN:
        logger.info("Webhook verification successful.")
        return Response(content=hub_challenge, media_type="text/plain")
    else:
        logger.warning("Webhook verification failed. Mode or token mismatch.")
        raise HTTPException(status_code=403, detail="Forbidden: Verification token mismatch.")

# --- Main Webhook Endpoint for Receiving Messages ---
@app.post("/webhook", tags=["Webhook"], summary="Receive WhatsApp Messages")
async def webhook_handler(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Error parsing webhook payload: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid payload format.")

    logger.info(f"Received webhook payload: {payload}")

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_id = metadata.get("phone_number_id")

            if not phone_id:
                logger.warning("Missing phone_number_id in webhook metadata.")
                continue

            tenant = tenant_by_phone_id(phone_id, db)
            if not tenant:
                logger.warning(f"Tenant not found for phone_id: {phone_id}")
                continue

            for msg_data in value.get("messages", []):
                sender_phone = msg_data.get("from")
                text_content = msg_data.get("text", {}).get("body", "")
                whatsapp_msg_id = msg_data.get("id")

                if not all([sender_phone, text_content, whatsapp_msg_id]):
                    logger.warning(f"Incomplete message data received: {msg_data}")
                    continue

                # Duplicate message guard
                existing_message = db.query(Message).filter_by(wa_msg_id=whatsapp_msg_id).first()
                if existing_message:
                    logger.info(f"Skipping duplicate WhatsApp message ID: {whatsapp_msg_id}")
                    continue

                # Save incoming message
                try:
                    db_message = Message(
                        tenant_id=tenant.id,
                        wa_msg_id=whatsapp_msg_id,
                        role="user",
                        text=text_content
                    )
                    db.add(db_message)
                    db.commit()
                    db.refresh(db_message) # Refresh to get ID and other defaults if any
                    logger.info(f"Saved incoming message ID {db_message.id} (WA ID: {whatsapp_msg_id})")
                except IntegrityError as e:
                    db.rollback()
                    logger.error(f"IntegrityError saving message (WA ID: {whatsapp_msg_id}): {e}", exc_info=True)
                    continue # Skip processing this message
                except Exception as e:
                    db.rollback()
                    logger.error(f"Error saving message (WA ID: {whatsapp_msg_id}): {e}", exc_info=True)
                    continue

                # Build chat history (last 10 messages, including current one)
                chat_history_query = (
                    db.query(Message)
                      .filter_by(tenant_id=tenant.id)
                      .order_by(Message.id.desc())
                      .limit(10)
                )
                history_messages = chat_history_query.all()[::-1] # Reverse to get chronological order
                
                chat_for_ai = [
                    {"role": "system", "content": tenant.system_prompt}
                ] + [{"role": m.role, "content": m.text} for m in history_messages]

                # Offload AI processing and reply to a background task
                background_tasks.add_task(
                    handle_ai_reply,
                    tenant=tenant,
                    chat_context=chat_for_ai,
                    sender_phone=sender_phone,
                    db_session_factory=lambda: next(get_db()) # Pass a way to get a new session
                )
                logger.info(f"Added AI reply task to background for WA message ID: {whatsapp_msg_id}")

    return {"status": "received", "message": "Webhook processed successfully."}

# --- Background Task for AI Reply Processing ---
async def handle_ai_reply(
    tenant: Tenant, # Use type hint if Tenant model is available
    chat_context: list[dict],
    sender_phone: str,
    db_session_factory # Callable that provides a new DB session
):
    db = None
    try:
        db = db_session_factory()
        logger.info(f"Background task: Generating AI reply for tenant {tenant.id} to {sender_phone}")
        
        # Ensure OPENAI_API_KEY is available for the background task context
        if not os.getenv("OPENAI_API_KEY"):
            logger.error("OPENAI_API_KEY not available in background task.")
            return

        # Re-initialize AsyncOpenAI client if it's not safe to share across threads/tasks
        # or ensure it's designed for such usage. For this example, we assume it can be reused
        # or re-initialized if needed. If ai object was global and properly configured, it might be usable.
        local_ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY").strip())

        response = await local_ai.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"), # Make model configurable
            messages=chat_context,
        )
        ai_answer = response.choices[0].message.content.strip()
        logger.info(f"Background task: AI generated answer: '{ai_answer[:100]}...' for tenant {tenant.id}")

        # Save AI's response to the database
        db_ai_message = Message(
            tenant_id=tenant.id,
            role="assistant",
            text=ai_answer,
            # wa_msg_id could be linked to the request or a new one generated by WhatsApp API response
        )
        db.add(db_ai_message)
        db.commit()
        logger.info(f"Background task: Saved AI response for tenant {tenant.id}")

        # Send reply via WhatsApp API
        # Ensure WH_TOKEN is available and stripped
        wh_token = tenant.wh_token.strip() # Assuming tenant object has wh_token
        if not wh_token:
            logger.error(f"WhatsApp token not available for tenant {tenant.id} in background task.")
            return

        async with httpx.AsyncClient() as client:
            send_url = f"https://graph.facebook.com/v{os.getenv('FB_GRAPH_VERSION', '19.0')}/{tenant.phone_id}/messages"
            headers = {
                "Authorization": f"Bearer {wh_token}",
                "Content-Type": "application/json",
            }
            json_payload = {
                "messaging_product": "whatsapp",
                "to": sender_phone,
                "type": "text",
                "text": {"body": ai_answer},
            }
            
            send_response = await client.post(send_url, headers=headers, json=json_payload)
            logger.info(f"Background task: WhatsApp API response status {send_response.status_code} for tenant {tenant.id}. Response: {send_response.text}")
            send_response.raise_for_status() # Raise an exception for HTTP error codes

    except httpx.HTTPStatusError as e:
        logger.error(f"Background task: HTTP error sending WhatsApp reply for tenant {tenant.id}: {e.response.text}", exc_info=True)
    except Exception as e:
        logger.error(f"Background task: Error processing AI reply for tenant {tenant.id}: {e}", exc_info=True)
    finally:
        if db:
            db.close()

# If you want to run this app directly using uvicorn for development:
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)

