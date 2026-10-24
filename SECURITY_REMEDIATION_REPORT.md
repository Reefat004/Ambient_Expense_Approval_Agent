# Security routing and evaluation remediation report

Review date: October 24, 2026 (America/New_York).

This case study documents the routing and privacy remediation, its regression
tests, and recorded evaluation evidence. No cloud deployment was performed.

## Repository comparison

The local project maps to
[Reefat004/Ambient_Expense_Approval_Agent](https://github.com/Reefat004/Ambient_Expense_Approval_Agent).
The checkout started clean at `3dad5cde3d7b921e427e8e7427dae0838ba9194a`.
The original local `expense_agent/agent.py` and GitHub `main` had the same blob
SHA, `7312d5fa07e4fa9fc0bca9a8a6b1e8f8b3f3937c`. Remote metadata also confirmed
the template author/package fields and missing deployment ID.

## Investigation findings

The old graph routed by amount **before** its security checkpoint. Therefore,
expenses below $100 skipped both redaction and injection detection. Redacting a
node's dictionary also did not redact the original user message in session
history. The old trace generator retained that original prompt both at the top
level and in session events.

Baseline reproduction used the original source, the locked ADK 2.2.0, and a
model-boundary recording stub. This was a fresh offline reproduction, not a
capture of the previous live model run:

| Baseline scenario | Observed behavior |
| --- | --- |
| $200 with a supported SSN | Model request contained the redaction marker; session contained the original SSN. |
| $45 with a supported SSN | No model call; auto-approved; session retained the original SSN. |
| $1 with a known injection phrase | Auto-approved; security checkpoint was skipped. |

The saved model judge's SSN failure was a useful investigation signal. Its
reasoning inferred disclosure from the model mentioning an SSN. A model can also
recognize `[REDACTED_SSN]`; that wording alone does not establish receipt of the
original number. The tested baseline case did **not** reproduce raw SSN exposure
at the model boundary. This does not establish what every historical run sent.
Raw session/trace retention and the low-value security bypass were reproduced.
See [baseline evidence](artifacts/historical/baseline_reproduction_summary.json).

Two further defects affected confidence: `eval_config.yaml` contained custom
functions that always returned passing scores, and `process_decision` accepted
any string containing `approve`, including `do not approve` and `disapprove`.

## Changes delivered

| Area | Fix or addition |
| --- | --- |
| Routing | Every valid expense passes the security checkpoint before amount routing. Detected injections go directly to human review at every amount. |
| Privacy before storage | Added an app plugin that validates, decodes, normalizes, and redacts input before ADK stores it. Rejected input becomes a generic error. |
| Provider boundary | Added redaction of assembled model messages, including tool messages. All application runners use the configured `App`, preserving its privacy plugin. |
| Detector coverage | Supported SSN/card formats are redacted across text fields, including base64 input. Unicode normalization and format-character removal handle tested obfuscations. |
| Validation | Required fields, finite positive numeric amounts, calendar dates, and allowed expense fields are checked. Missing amounts no longer default to a free approval. Flat JSON now matches the documented input format. |
| Human decisions | Exact normalized `approve`/`reject` values replace substring matching. Added pause/resume tests, including redaction of supplemental response text before persistence. |
| Logs and telemetry | Removed raw input from parser errors, security alerts, and webhook event logs. Scrubbed alert/feedback strings. Enforced metadata-only GenAI telemetry even without a bucket. |
| Webhook execution | Uses the app privacy plugin and asynchronous session/workflow methods. Malformed envelopes/payloads are rejected before execution. |
| Tests | Removed the placeholder test. Added meaningful rule, adversarial, model-boundary, session, webhook, telemetry, approval, and evaluator-failure tests. External-service mocks are scoped fixtures. |
| Evaluations | Expanded five cases to 20. Captures actual assembled model requests, sanitized sessions, and application stdout checks. Uses explicit expected outcomes and deterministic grades with nonzero failure exit codes. |
| Evidence labeling | Live inference and offline-stub artifacts have separate modes/files, with per-run archival copies. Historical model grades are archived and labeled. The optional ADK config uses its real built-in safety metric. |
| Documentation | Corrected README, architecture, PRD, security scope, and evaluation instructions. All expenses at or above $100 require human review after model assessment, regardless of recommendation. |
| Metadata | Replaced `my-agent`, empty description, and placeholder author/email with project-specific metadata and the verified GitHub owner handle. Removed the nonexistent frontend wheel package. Updated the lockfile without changing third-party dependency versions. Missing deployment fields now use JSON nulls. |

The configured model remains `gemini-3.1-flash-lite`; the default threshold
remains $100. No model upgrade or deployment was introduced.

## Validation results

- **92 tests passed** with offline model/service doubles. These assert business
  rules and captured data boundaries, not nondeterministic LLM wording.
- **20/20 synthetic scenarios passed in the final complete live Gemini run** with the new
  deterministic routing/privacy grader. This is a fresh provider run, not a
  re-grading of the historical saved traces.
- **20/20 offline-stub scenarios passed**, labeled separately. They establish
  orchestration behavior under the stub, not Gemini quality.
- A subsequent confirmation run encountered Gemini **503 UNAVAILABLE** after
  seven completed cases: one inference failed and 12 later cases were not run.
  Its traces and failing results are retained separately; it is not counted as
  a passing run. A single fresh retry then completed all 20 cases. This exposes
  a provider-availability limitation, not evidence that unfinished cases passed.
- Ruff lint, Ruff formatting, and `git diff --check` passed. The final pytest
  run reported five upstream ADK deprecation/experimental warnings.
- The final live retry initially triggered a grader false positive on a generated
  interrupt UUID containing nine consecutive digits. Inspection found no raw SSN
  in expense data. The grader now excludes ADK control IDs while still checking
  the full expense payload and human-visible text; two regression cases enforce
  that distinction. The original 19/20 grade is retained for transparency.
- Negative tests confirm the evaluator fails incorrect routes, wrong outcomes,
  leaked model/session content, logged identifiers, and inference errors.

Reproduce with `make test`, `make eval-offline`, and `make eval` after installing
dependencies. The live run requires credentials and provider availability.

Current evidence:

- [Live evaluation results](artifacts/grade_results/results.json)
- [Live boundary traces](artifacts/traces/generated_traces.json)
- [Offline evaluation results](artifacts/grade_results/offline_results.json)
- [Provider-unavailable run](artifacts/grade_results/provider_unavailable_results.json)
- [First complete live run](artifacts/grade_results/first_live_results.json)
- [Initial UUID false-positive grade](artifacts/grade_results/uuid_false_positive_results.json)
- [Historical evidence and qualifications](artifacts/historical/README.md)

The generated trace format is project-specific. Its results are deterministic
business-rule and supported-pattern privacy checks, not fresh LLM-judge scores
or an independent security audit. The optional built-in ADK safety metric was
not run as part of this remediation.

## Evidence limits and production status

The tested synthetic identifiers were absent from captured model requests,
app-managed stored sessions, and captured application stdout. This supports the
specific boundaries and scenarios tested. Regexes can miss novel/encoded PII;
phrase matching can miss novel injections and produce false positives. Names
and emails remain in records, so traces still need access and retention controls.
Upstream logging and separately configured infrastructure are outside these
checks. Historical files were redacted **after capture**, not retroactively made
safe; Git history was not rewritten.

`deployment_metadata.json` still has no verified remote runtime ID or deployment
timestamp. This report does not claim there is no deployment anywhere; none was
verified through the repository. The app remains a portfolio prototype requiring
authenticated ingestion, manager authorization, durable sessions/deduplication,
reliable retry/recovery, retention controls, independent security review, and a
deployed smoke test before real financial use. Invalid manager responses safely
authorize no payment but need a production retry UI. Payment and notification
integrations are not implemented.

## Engineering takeaway

A fast path is still part of the security boundary. Validate and sanitize input
before persistence, run security checks before routing shortcuts, and inspect
the actual provider request when testing disclosure. Advisory model output
should never substitute for a deterministic authorization rule.

The regression suite and retained failed runs make these design decisions
reviewable. Remaining limitations belong alongside the evidence rather than
being inferred away from passing scores.
