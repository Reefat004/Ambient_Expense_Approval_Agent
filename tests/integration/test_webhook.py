import base64
import json

import httpx
import pytest

from expense_agent.main import app


@pytest.mark.asyncio
async def test_pubsub_uses_privacy_plugin(offline_services):
    from expense_agent.main import session_service

    expense = {
        "amount": 200,
        "submitter": "alice@example.com",
        "category": "meals",
        "description": "SSN 123-45-6789",
        "date": "2026-10-24",
    }
    envelope = {
        "message": {
            "messageId": "pii-webhook-test",
            "data": base64.b64encode(json.dumps(expense).encode()).decode(),
        },
        "subscription": "tests/webhook",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/pubsub", json=envelope)
        assert response.status_code == 200
        duplicate = await client.post("/pubsub", json=envelope)
        assert duplicate.json()["status"] == "already_processed"
    assert len(offline_services.requests) == 1
    session = await session_service.get_session(
        app_name="expense_agent", user_id="webhook", session_id="pii-webhook-test"
    )
    assert "123-45-6789" not in session.model_dump_json() + json.dumps(
        offline_services.requests
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"message": "oops"},
        {"message": {"data": "not base64"}},
        {"message": {"data": "e30="}},
    ],
)
async def test_bad_webhooks_rejected(offline_services, body):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/pubsub", json=body)
    assert response.status_code == 400
    assert offline_services.requests == []
