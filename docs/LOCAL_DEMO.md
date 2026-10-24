# Local demo and API guide

The checked-in examples contain synthetic expense data. Start from the repository
root after `uv sync --locked --all-extras`.

## No-key HTTP demo

In one terminal:

```bash
make serve
```

In another terminal:

```bash
curl --fail-with-body -sS http://localhost:8080/pubsub \
  -H 'Content-Type: application/json' \
  --data-binary @examples/pubsub-small.json
```

Expected response:

```json
{"status":"ok","message_id":"demo-small-001"}
```

The sample is a clean $45 expense, so it is auto-approved without a model call.
The server prints a structured decision log. Sending the same request again
returns `{"status":"already_processed","message_id":"demo-small-001"}` within
that server process. Restarting the server clears its in-memory sessions and
its duplicate records.

Open http://localhost:8080/docs for the local FastAPI API explorer.

## Request contract

`POST /pubsub` accepts a Pub/Sub push envelope:

```json
{
  "message": {
    "messageId": "unique-message-id",
    "data": "<base64-encoded expense JSON>"
  },
  "subscription": "projects/demo/subscriptions/expenses"
}
```

The decoded expense contains `amount`, `submitter`, `category`, `description`,
and `date`. The amount must be a positive finite JSON number, dates must use
`YYYY-MM-DD` and represent a real calendar date, and unknown expense fields are
rejected. Malformed envelopes, base64, JSON, or expense fields return HTTP 400.
Use a new message ID for each new event.

HTTP `ok` means the workflow reached its current stopping point. An expense that
requires review can be paused; `ok` does not mean the manager approved it.
The endpoint does not expose a manager approval API. It is a local ingestion
example; authenticate event delivery and manager actions before hosting it.

The JSON files named `expense-*.json` are direct graph/playground input, whereas
`pubsub-small.json` is an HTTP envelope. To build another local envelope:

```bash
uv run python - <<'PY'
import base64
import json
from pathlib import Path

expense = json.loads(Path("examples/expense-review.json").read_text())["data"]
envelope = {
    "message": {
        "messageId": "demo-review-001",
        "data": base64.b64encode(json.dumps(expense).encode()).decode(),
    },
    "subscription": "projects/demo/subscriptions/expenses",
}
Path("/tmp/expense-review-envelope.json").write_text(json.dumps(envelope))
PY
curl --fail-with-body -sS http://localhost:8080/pubsub \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/expense-review-envelope.json
```

This $150 route requires live model credentials.

## Human review

For interactive testing, install `google-agents-cli`, configure credentials, and
run `make playground`. Paste an expense sample into a session and use the
playground's input-response flow for the paused request.

In the ADK API, retain the `adk_request_input` call's ID and send a matching
function response **in the same session**. Its response is
`{"decision":"approve"}` or `{"decision":"reject"}`. The implementation uses:

```python
message = types.Content(
    role="user",
    parts=[types.Part(function_response=types.FunctionResponse(
        name="adk_request_input",
        id=approval_call.id,
        response={"decision": "approve"},
    ))],
)
```

Here `types` is `google.genai.types` and `approval_call` is the function call
from the paused run. Pass the message to the existing runner's `run_async` with
the original user/session IDs. See the executable pause/resume examples in
[the integration tests](../tests/integration/test_agent.py).

Sending the decision as a new JSON expense is not a resume. Ambiguous decisions
such as `do not approve` return `invalid_decision` and authorize no approval.
A production review interface still needs authentication and a supported retry
flow after an invalid decision.

## Credentials and configuration

Copy `.env.example` to `.env` and set `GEMINI_API_KEY` for local Gemini calls.
If both `GOOGLE_API_KEY` and `GEMINI_API_KEY` exist, the SDK prefers
`GOOGLE_API_KEY`; remove unintended conflicting settings from your shell.

Vertex AI is also supported using application default credentials and
`GOOGLE_GENAI_USE_VERTEXAI=True`, `GOOGLE_CLOUD_PROJECT`, and
`GOOGLE_CLOUD_LOCATION`. Model and threshold defaults are in
[`expense_agent/config.py`](../expense_agent/config.py).
No cloud credentials are needed for `make test` or `make eval-offline`.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| HTTP 400 | Use a Pub/Sub envelope, valid base64, and all five expense fields. Direct graph JSON belongs in the playground. |
| `already_processed` | Give a new event a new message ID; restarting clears local memory. |
| Review appears stuck | A high-value or flagged expense intentionally pauses until its matching manager response. |
| Authentication failure | Confirm the selected provider and environment variables; do not paste keys into issues. |
| Model 503 or timeout | The provider may be unavailable. Keep the failed evidence and retry later; use offline evaluation for deterministic checks. |
| Model 404 | Verify model access and location before changing the configured model. |
| State disappears after restart | The local endpoint uses in-memory storage; durable sessions are future work. |

For detector coverage and the boundaries these demos do not test, read
[SECURITY.md](../SECURITY.md).
