# Security and privacy scope

This project is an engineering prototype. Its tests and evaluation artifacts are
not an independent security audit or evidence of production readiness.

## Implemented controls

- `ExpensePrivacyPlugin` validates and normalizes JSON before ADK appends user
  messages to session history. Base64 payloads are decoded first. Rejected input
  is replaced with a generic error, without echoing its contents.
- `security_checkpoint` runs for every valid amount before threshold routing.
  Known suspicious instructions in any text field bypass the model and request
  human review, including expenses below $100.
- SSNs (nine contiguous digits or common hyphen/space formats) and card-like
  sequences (13–19 digits, optionally separated by spaces/hyphens) are replaced
  with markers throughout text fields. Unicode compatibility normalization and
  removal of format characters handle some common obfuscation.
- The privacy plugin also scrubs assembled model contents at the provider
  boundary. Application runners must use `Runner(app=adk_app, ...)`; constructing
  a runner from only `root_agent` omits application plugins.
- Application errors and security alerts omit raw input. Feedback and tool alert
  strings receive the same supported-pattern redaction. Webhook event bodies
  are no longer logged. GenAI telemetry setup enforces `NO_CONTENT` even without
  a logging bucket.
- Clean expenses below $100 are auto-approved. Every expense at or above $100
  requires an explicit human decision after model assessment. The model has no
  approval tool. Only an exact `approve` or `reject` decision is accepted;
  ambiguous decisions produce `invalid_decision` and authorize no payment.

## Limits and remaining work

Regexes are limited detectors: they can miss encoded, novel, or unusual PII and
can redact unrelated numeric references. Emails and names remain in sanitized
expense records. Treat sessions, traces, and feedback as sensitive records with
appropriate access controls and retention policies. Detection of a few injection
phrases does not prove resistance to arbitrary prompt injection.

The input exists in application memory before the hook. These controls do not
cover upstream request logging, SDK instrumentation before callbacks, provider
retention, independently configured telemetry, or custom runners that omit the
plugin. Do not send real employee PII to the playground or evaluation suite.

The webhook has in-memory sessions and process-local duplicate detection. It
needs authenticated Pub/Sub delivery, authorization for manager decisions,
durable state, reliable retries, and a verified deployed smoke test before use
with real financial requests. An invalid manager decision currently ends that
attempt without approval; a production review UI needs a supported retry flow.
No real reimbursement or notification integration is implemented.

`deployment_metadata.json` has no remote runtime ID. No live deployment is
verified. Credentials belong in environment/managed secret storage; `.env` is
ignored by Git, but that alone is not a repository-wide secret audit.

## Evidence and reporting

`make test` runs offline deterministic regression tests; `make eval` uses the
configured Gemini model with synthetic inputs and deterministic routing/privacy
grading. `make eval-offline` uses a model stub and labels its results accordingly.
A pass checks the specified scenarios and observed application boundaries only.
Historical model-graded artifacts under `artifacts/historical/` were redacted
after capture; Git history is unchanged. See `SECURITY_REMEDIATION_REPORT.md`.

For a suspected vulnerability, contact the repository owner privately through a
verified channel. Do not include live PII or credentials in a public issue.
