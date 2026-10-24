"""Deterministic input validation and limited SSN/card redaction.

These patterns are a guardrail, not a general PII detector or an injection proof.
"""

import base64
import json
import re
import unicodedata
from datetime import date
from typing import Any

from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExpenseData(BaseModel):
    """Required fields; invalid amounts must never become free approvals."""

    model_config = ConfigDict(extra="forbid")
    amount: float = Field(gt=0, allow_inf_nan=False)
    submitter: str = Field(min_length=1, max_length=320)
    category: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    date: str

    @field_validator("amount", mode="before")
    @classmethod
    def numeric_amount(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Amount must be a JSON number")
        return value

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Date must use YYYY-MM-DD")
        return value


SSN = re.compile(r"(?<!\d)(?:\d{3}[- ]\d{2}[- ]\d{4}|\d{9})(?!\d)")
CARD = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?![ -]?\d)")
INJECTION = re.compile(
    r"ignore\s+(?:(?:all|the|previous|prior)\s+)*(?:instructions|rules)"
    r"|bypass|override|auto[ -]?approve|approve\s+immediately"
    r"|do\s+not\s+flag|system\s+prompt|you\s+are\s+now",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


def redact(value: Any) -> Any:
    """Redact supported identifiers recursively, including non-description fields."""
    if isinstance(value, str):
        return SSN.sub("[REDACTED_SSN]", CARD.sub("[REDACTED_CC]", normalize(value)))
    if isinstance(value, dict):
        return {redact(k): redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def decode_expense(text: str) -> dict:
    """Accept flat JSON, a data wrapper, or strict base64 in the data wrapper."""
    event = json.loads(text)
    if not isinstance(event, dict):
        raise ValueError("Expected an object")
    data = event.get("data", event)
    if isinstance(data, str):
        data = json.loads(base64.b64decode(data, validate=True).decode("utf-8"))
    return ExpenseData.model_validate(data).model_dump()


def has_injection(expense: dict) -> bool:
    return any(
        INJECTION.search(normalize(v)) for v in expense.values() if isinstance(v, str)
    )


class ExpensePrivacyPlugin(BasePlugin):
    """Sanitize before ADK appends user input to session history."""

    def __init__(self):
        super().__init__(name="expense_privacy")

    async def before_model_callback(self, *, callback_context, llm_request):
        # Defense in depth at the provider boundary, including tool messages.
        llm_request.contents = [
            types.Content.model_validate(redact(content.model_dump(exclude_none=True)))
            for content in llm_request.contents
        ]

    async def on_user_message_callback(self, *, invocation_context, user_message):
        if any(p.function_response for p in user_message.parts or []):
            for part in user_message.parts:
                if part.function_response:
                    response = part.function_response.response
                    sanitized = redact(response)
                    # ADK has already taken references for resume_inputs.
                    response.clear()
                    response.update(sanitized)
            return user_message
        try:
            if any(p.text is None for p in user_message.parts or []):
                raise ValueError("Only JSON text is supported")
            text = "".join(p.text for p in user_message.parts or [])
            payload = {"data": redact(decode_expense(text))}
        except (ValueError, TypeError):
            # No input fragments or validation exception reprs in errors/history.
            payload = {"error": "Invalid expense payload"}
        # ADK 2.2 resolves node_input before invoking this hook. Mutate the
        # Content too, so the workflow input and persisted message agree.
        user_message.parts = [types.Part.from_text(text=json.dumps(payload))]
        return user_message
