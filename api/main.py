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

# Assuming the directory structure is api/main.py, api/deps.py, api/models.py, api/routers/admin.py
from .deps import get_db, tenant_by_phone_id # Adjusted to relative import if main is part of a package
from .models import Message, Tenant # Adjusted to relative import
from .routers import admin as admin_router # Import the admin router

# --- Environment Variable Sanitization ---
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
    description="Handles WhatsApp webhooks, processes messages using AI, and provides admin functionalities.",
    version="1.0.1" # Incremented version
)

# Include the admin router
app.include_router(admin_router.router)

# Initialize OpenAI client
ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Logging Configuration ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

@app.on_event("startup")
def startup_event():
    logger.info("Application startup: running Alembic migrations.")
    try:
        # Ensure alembic.ini path is correct relative to this file's location
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
        alembic_cfg = Config(cfg_path)
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations completed successfully.")
    except Exception as e:
        logger.error(f"Error during Alembic migrations: {e}", exc_info=True)

# --- Health Check Endpoint ---
@app.get("/health", tags=["Monitoring"], summary="Perform a Health Check")
async def health_check():
    return {"status": "ok", "message": "Service is healthy"}

# --- Webhook Verification Endpoint ---
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

                existing_message = db.query(Message).filter_by(wa_msg_id=whatsapp_msg_id).first()
                if existing_message:
                    logger.info(f"Skipping duplicate WhatsApp message ID: {whatsapp_msg_id}")
                    continue

                try:
                    db_message = Message(
                        tenant_id=tenant.id,
                        wa_msg_id=whatsapp_msg_id,
                        role="user",
                        text=text_content
                    )
                    db.add(db_message)
                    db.commit()
                    db.refresh(db_message)
                    logger.info(f"Saved incoming message ID {db_message.id} (WA ID: {whatsapp_msg_id})")
                except IntegrityError as e:
                    db.rollback()
                    logger.error(f"IntegrityError saving message (WA ID: {whatsapp_msg_id}): {e}", exc_info=True)
                    continue
                except Exception as e:
                    db.rollback()
                    logger.error(f"Error saving message (WA ID: {whatsapp_msg_id}): {e}", exc_info=True)
                    continue

                chat_history_query = (
                    db.query(Message)
                      .filter_by(tenant_id=tenant.id)
                      .order_by(Message.id.desc())
                      .limit(10)
                )
                history_messages = chat_history_query.all()[::-1]
                
                chat_for_ai = [
                    {"role": "system", "content": tenant.system_prompt}
                ] + [{"role": m.role, "content": m.text} for m in history_messages]

                background_tasks.add_task(
                    handle_ai_reply,
                    tenant=tenant,
                    chat_context=chat_for_ai,
                    sender_phone=sender_phone,
                    db_session_factory=lambda: next(get_db())
                )
                logger.info(f"Added AI reply task to background for WA message ID: {whatsapp_msg_id}")

    return {"status": "received", "message": "Webhook processed successfully."}

# --- Background Task for AI Reply Processing ---
async def handle_ai_reply(
    tenant: Tenant,
    chat_context: list[dict],
    sender_phone: str,
    db_session_factory
):
    db = None
    try:
        db = db_session_factory()
        logger.info(f"Background task: Generating AI reply for tenant {tenant.id} to {sender_phone}")
        
        if not os.getenv("OPENAI_API_KEY"):
            logger.error("OPENAI_API_KEY not available in background task.")
            return

        local_ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY").strip())

        response = await local_ai.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            messages=chat_context,
        )
        ai_answer = response.choices[0].message.content.strip()
        logger.info(f"Background task: AI generated answer: '{ai_answer[:100]}...' for tenant {tenant.id}")

        db_ai_message = Message(
            tenant_id=tenant.id,
            role="assistant",
            text=ai_answer,
        )
        db.add(db_ai_message)
        db.commit()
        logger.info(f"Background task: Saved AI response for tenant {tenant.id}")

        wh_token = tenant.wh_token.strip()
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
            send_response.raise_for_status()

    except httpx.HTTPStatusError as e:
        logger.error(f"Background task: HTTP error sending WhatsApp reply for tenant {tenant.id}: {e.response.text}", exc_info=True)
    except Exception as e:
        logger.error(f"Background task: Error processing AI reply for tenant {tenant.id}: {e}", exc_info=True)
    finally:
        if db:
            db.close()

