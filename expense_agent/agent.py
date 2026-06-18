# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Ambient agent that processes expense report events.

Uses ADK 2.0 graph-based workflows to process expense approvals:
- Under $100: auto-approved instantly.
- $100 or more: analyzed by an LLM for risk, triggers an alert log,
  and pauses for human approval via RequestInput (HITL).
- Security Checkpoint: scrubs SSN and CC numbers and flags/bypasses
  LLM review for potential prompt injections.
"""

import base64
import json
import re
from typing import Any

from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import Workflow
from google.genai import types
from pydantic import BaseModel, Field

from .config import config

# ---------------------------------------------------------------------------
# Pydantic schemas for structured data flow
# ---------------------------------------------------------------------------


class ExpenseData(BaseModel):
    """Expense report data extracted from the incoming email/event."""

    amount: float = Field(description="Expense amount in USD")
    submitter: str = Field(description="Email of the person who submitted")
    category: str = Field(description="Expense category, e.g. travel, meals")
    description: str = Field(description="What the expense is for")
    date: str = Field(description="Date of the expense (YYYY-MM-DD)")


# ---------------------------------------------------------------------------
# Function nodes & Security Checkpoint
# ---------------------------------------------------------------------------


def parse_expense_email(node_input: str) -> Event:
    """Parse a Pub/Sub trigger event and extract expense data.

    Handles both base64-encoded payloads (from real Pub/Sub) and
    plain JSON payloads (for local testing/playground).
    """
    try:
        event = json.loads(node_input)
    except json.JSONDecodeError:
        err_msg = f"Invalid JSON: {node_input[:200]}"
        return Event(
            content=types.Content(
                role="model", parts=[types.Part.from_text(text=err_msg)]
            ),
            output={"error": err_msg},
        )

    data = event.get("data", {})

    if isinstance(data, str):
        try:
            # Pub/Sub payload data is base64-encoded
            decoded_bytes = base64.b64decode(data)
            data = json.loads(decoded_bytes.decode("utf-8"))
        except Exception:
            err_msg = f"Failed to decode base64 data: {data[:200]}"
            return Event(
                content=types.Content(
                    role="model", parts=[types.Part.from_text(text=err_msg)]
                ),
                output={"error": err_msg},
            )

    return Event(
        output={
            "amount": float(data.get("amount", 0)),
            "submitter": data.get("submitter", "unknown"),
            "category": data.get("category", "other"),
            "description": data.get("description", ""),
            "date": data.get("date", ""),
        }
    )


def route_by_amount(node_input: dict, ctx: Context) -> Event:
    """Route expenses based on the configured dollar threshold.

    If amount >= threshold, routes to 'NEEDS_REVIEW'.
    Otherwise, routes to 'AUTO_APPROVE'.
    """
    ctx.state["expense_data"] = node_input
    amount = node_input.get("amount", 0.0)
    if amount >= config.review_threshold:
        ctx.route = "NEEDS_REVIEW"
    else:
        ctx.route = "AUTO_APPROVE"
    return Event(output=node_input)


def security_checkpoint(node_input: dict, ctx: Context) -> Event:
    """Scrub personal data (SSN, credit cards) and detect prompt injection.

    If prompt injection is found, bypasses the LLM reviewer entirely
    by routing directly to human approval ('SUSPICIOUS').
    """
    description = node_input.get("description", "")

    # 1. Scrub SSNs & Credit Cards
    redacted_categories = []
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", description):
        description = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", description)
        redacted_categories.append("SSN")
    if re.search(r"\b(?:\d[ -]*?){13,19}\b", description):
        description = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED_CC]", description)
        redacted_categories.append("Credit Card")

    node_input["description"] = description
    ctx.state["expense_data"] = node_input
    ctx.state["redacted_categories"] = redacted_categories

    # 2. Defend against prompt injection
    prompt_injection_triggers = [
        "ignore previous instructions",
        "ignore the rules",
        "bypass",
        "override",
        "auto-approve",
        "approve immediately",
        "do not flag",
        "system prompt",
        "you are now",
    ]
    description_lower = description.lower()
    has_injection = any(
        trigger in description_lower for trigger in prompt_injection_triggers
    )

    if has_injection:
        log_entry = {
            "severity": "WARNING",
            "message": f"SECURITY ALERT: Prompt injection attempt detected: '{description}'",
            "alert_type": "prompt_injection_security_event",
            "submitter": node_input.get("submitter", "unknown"),
            "amount": node_input.get("amount", 0.0),
        }
        print(json.dumps(log_entry), flush=True)
        ctx.state["security_flag"] = True
        ctx.route = "SUSPICIOUS"
        return Event(output=node_input)

    ctx.route = "CLEAN"
    return Event(output=node_input)


def auto_approve(node_input: dict) -> Event:
    """Auto-approve a low-value expense and log the decision."""
    log_entry = {
        "severity": "INFO",
        "message": (
            f"Expense auto-approved: ${node_input['amount']:.2f} "
            f"from {node_input['submitter']}"
        ),
        "decision": "approved",
        "amount": node_input["amount"],
        "submitter": node_input["submitter"],
        "category": node_input["category"],
    }
    print(json.dumps(log_entry), flush=True)
    msg = f"Expense auto-approved: ${node_input['amount']:.2f} from {node_input['submitter']}."
    return Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]),
        output={"status": "approved", **node_input},
    )


# ---------------------------------------------------------------------------
# LLM review agent & alerts
# ---------------------------------------------------------------------------


def emit_expense_alert(
    submitter: str,
    amount: float,
    category: str,
    risk_summary: str,
) -> dict:
    """Emit a structured warning log alerting finance to review a high-value expense.

    Args:
        submitter: Who submitted the expense.
        amount: The expense amount in USD.
        category: The expense category.
        risk_summary: Summary of why this expense needs review.

    Returns:
        A status dictionary confirming the alert was emitted.
    """
    log_entry = {
        "severity": "WARNING",
        "message": (
            f"Expense review alert: ${amount:.2f} from {submitter} - {risk_summary}"
        ),
        "alert_type": "expense_review",
        "submitter": submitter,
        "amount": amount,
        "category": category,
        "risk_summary": risk_summary,
    }
    print(json.dumps(log_entry), flush=True)
    return {"status": "alert_emitted", "submitter": submitter, "amount": amount}


review_agent = Agent(
    name="review_agent",
    model=config.model,
    mode="single_turn",
    instruction="""You are an expense review agent. You receive expense reports
of $100 or more that need review before approval.

Analyze the expense and:
1. Check for risk factors: unusual category for the amount, vague description,
   suspiciously round numbers, very high value (>$1000), or potential policy
   violations.
2. Call the `emit_expense_alert` tool with the submitter, amount, category,
   and a brief risk summary explaining why this expense needs human review.
3. Return a structured review.

Your review MUST include:
- **Amount**: The expense amount
- **Submitter**: Who submitted it
- **Category**: The expense category
- **Risk level**: low, medium, or high
- **Risk factors**: What flags you found (if any)
- **Recommendation**: approve, request-more-info, or escalate""",
    input_schema=ExpenseData,
    tools=[emit_expense_alert],
)


# ---------------------------------------------------------------------------
# Human-in-the-loop (HITL) nodes
# ---------------------------------------------------------------------------


def request_approval(node_input: Any, ctx: Context):
    """Pause the workflow and wait for a human manager to approve/reject."""
    expense = ctx.state.get("expense_data", {})
    message = "Expense requires manager approval. Approve or reject."
    if ctx.state.get("security_flag"):
        message = "⚠️ SECURITY ALERT: Potential prompt injection detected! Expense requires urgent manager approval. Approve or reject."
    yield RequestInput(
        message=message,
        payload=expense,
    )


def process_decision(node_input: Any, ctx: Context) -> Event:
    """Process the human manager's decision and log the outcome."""
    decision = "unknown"
    if isinstance(node_input, dict):
        decision = node_input.get("decision", "unknown")
    elif isinstance(node_input, str):
        decision = "approve" if "approve" in node_input.lower() else "reject"

    approved = decision == "approve"
    expense = ctx.state.get("expense_data", {})
    status = "approved" if approved else "rejected"

    log_entry = {
        "severity": "INFO" if approved else "WARNING",
        "message": f"Expense {status} by manager",
        "decision": status,
    }
    print(json.dumps(log_entry), flush=True)

    submitter = expense.get("submitter", "unknown")
    amount = expense.get("amount", 0.0)
    category = expense.get("category", "")
    description = expense.get("description", "")
    date = expense.get("date", "")

    parts = [f"${amount:.2f} expense from {submitter} has been {status}."]
    if description:
        parts.append(f'"{description}" ({category}) on {date}.')
    if approved:
        parts.append(
            "The expense has been logged and will be processed for reimbursement."
        )
    else:
        parts.append(
            "The submitter will be notified and may resubmit with additional documentation."
        )

    msg = " ".join(parts)
    return Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]),
        output={"status": status, "message": msg},
    )


# ---------------------------------------------------------------------------
# Workflow and App definition
# ---------------------------------------------------------------------------

root_agent = Workflow(
    name="expense_processor",
    edges=[
        ("START", parse_expense_email, route_by_amount),
        (
            route_by_amount,
            {
                "AUTO_APPROVE": auto_approve,
                "NEEDS_REVIEW": security_checkpoint,
            },
        ),
        (
            security_checkpoint,
            {
                "CLEAN": review_agent,
                "SUSPICIOUS": request_approval,
            },
        ),
        (review_agent, request_approval),
        (request_approval, process_decision),
    ],
)

app = App(
    root_agent=root_agent,
    name="expense_agent",
)
