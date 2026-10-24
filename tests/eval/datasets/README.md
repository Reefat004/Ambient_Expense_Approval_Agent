# Synthetic regression scenarios

`basic-dataset.json` contains 20 synthetic cases and expected deterministic
business outcomes. SSNs/cards in this source fixture are deliberately fake test
inputs. Do not replace them with employee data.

Run `make eval` for fresh live Gemini inference and deterministic grading, or
`make eval-offline` for the explicitly labeled model-stub run. Cases cover clean
routing, exact threshold boundaries, manual rejection, ambiguous decisions,
supported PII across fields and base64 input, low-value injections, Unicode
obfuscation, invalid amounts/shapes, and flat JSON.

Each case has a JSON-text `prompt`, an `expected` object with `model_called`,
`review_required`, and `status`, and optionally `decision`/`security_alert`.
The project harness supplies synthetic human decisions by matching the
`adk_request_input` call ID; it does not send a decision as a new expense.

Generated traces include sanitized sessions and assembled model requests. They
do not copy the raw source prompt into a top-level artifact field. The grader
checks outcomes and privacy evidence and fails with a nonzero exit code.
Model-stub inference, live inference, and historical model-judge grades are
labeled separately. No artifact is an independent security audit.

`eval_config.yaml` is only for the separate optional agents-cli built-in safety
metric. The project deterministic trace format is consumed by `grade_traces.py`,
not by `agents-cli eval compare` or `agents-cli eval grade`.
