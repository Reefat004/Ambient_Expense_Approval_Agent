import base64
import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from expense_agent.agent import app as adk_app

# Telemetry: Set otel_to_cloud=False
os.environ["OTEL_TO_CLOUD"] = "False"

# Logging: Use standard Python logging for console logs
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

session_service = InMemorySessionService()

# Instantiate the Runner
runner = Runner(
    app=adk_app,
    session_service=session_service,
)

app = FastAPI(
    title="Ambient Expense Agent",
    description="Pub/Sub triggered ADK 2.0 graph workflow for expense approvals.",
)


@app.post("/pubsub")
async def pubsub_webhook(request: Request):
    """Webhook endpoint for Pub/Sub push subscriptions."""
    try:
        envelope = await request.json()
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad Request: Invalid JSON") from e

    if not isinstance(envelope, dict) or not envelope:
        raise HTTPException(status_code=400, detail="Bad Request: Empty body")

    message = envelope.get("message")
    if not isinstance(message, dict) or not message:
        raise HTTPException(
            status_code=400, detail="Bad Request: Missing 'message' in envelope"
        )

    subscription = envelope.get("subscription", "unknown-subscription")
    if not isinstance(subscription, str):
        raise HTTPException(status_code=400, detail="Bad Request: Invalid subscription")

    # Normalize subscription path to keep session ID readable
    # e.g., projects/my-project/subscriptions/expense-sub -> expense-sub
    normalized_sub = subscription.split("/")[-1]

    message_id = message.get("messageId", "unknown-id")
    data_b64 = message.get("data")

    if not data_b64:
        raise HTTPException(
            status_code=400, detail="Bad Request: Missing 'data' in message"
        )

    try:
        data_json_str = base64.b64decode(data_b64, validate=True).decode("utf-8")
        data_json = json.loads(data_json_str)
        from expense_agent.security import decode_expense

        decode_expense(json.dumps({"data": data_json}))
    except (ValueError, TypeError) as e:
        logger.warning("Invalid expense payload")
        raise HTTPException(
            status_code=400, detail="Bad Request: Invalid base64 or JSON data"
        ) from e

    logger.info("Received expense event")

    # Construct an input message for the ADK workflow
    payload_str = json.dumps({"data": data_json})
    start_message = types.Content(
        role="user", parts=[types.Part.from_text(text=payload_str)]
    )

    # Use normalized subscription name as the user_id (the "ambient system" user)
    # and message_id as session_id to isolate workflow state per event
    user_id = normalized_sub
    session_id = message_id

    # Ensure session exists
    try:
        await session_service.create_session(
            user_id=user_id, app_name=adk_app.name, session_id=session_id
        )
    except AlreadyExistsError:
        logger.info("Session already exists. Skipping duplicate execution.")
        return {"status": "already_processed", "message_id": message_id}

    # Run the workflow
    logger.info("Executing workflow...")
    async for _event in runner.run_async(
        new_message=start_message,
        user_id=user_id,
        session_id=session_id,
    ):
        pass

    logger.info("Workflow execution finished.")

    return {"status": "ok", "message_id": message_id}
