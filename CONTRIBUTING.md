# Contributing

Use Python 3.11–3.13 and `uv`. Install the locked development environment:

```bash
uv sync --locked --all-extras
```

Before opening a pull request:

```bash
make lint
make test
```

Run offline scenarios without replacing the committed reference artifacts:

```bash
PYTHONPATH=. uv run --no-sync python tests/eval/generate_traces.py \
  --offline --output /tmp/expense-eval/traces.json
PYTHONPATH=. uv run --no-sync python tests/eval/grade_traces.py \
  --traces /tmp/expense-eval/traces.json --output /tmp/expense-eval/results.json
```

CI runs these checks without model credentials. Use `make eval` when a change
requires live model validation; it makes provider calls and updates local
artifacts. Keep inference failures visible and label model-stub results
separately. Do not describe either type of evaluation as a security audit.

## Change guidelines

- Keep amount-based approval rules in deterministic code. Model recommendations
  must not authorize high-value expenses.
- Use the configured `App` when constructing runners so its privacy plugin runs.
- Add regression tests for business rules and adversarial inputs. Inspect model
  requests, session data, and outcomes; avoid assertions about LLM prose.
- Use synthetic data only. Do not commit `.env`, credentials, employee records,
  or traces containing real personal data.
- Explain a behavior change and its validation in the pull request. Update the
  README/API guide when changing input, routing, or pause/resume behavior.
- Preserve third-party copyright headers. If dependencies change, update
  `pyproject.toml` and `uv.lock` together.

Report suspected vulnerabilities privately through a verified channel to the
repository owner, as described in [SECURITY.md](SECURITY.md).
