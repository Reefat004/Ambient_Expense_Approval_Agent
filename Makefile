# Makefile for Ambient Expense Agent

.PHONY: install playground test lint serve generate-traces grade eval eval-offline

install:
	@echo "Installing project dependencies..."
	uv sync

playground:
	@echo "Launching the ADK playground..."
	agents-cli playground

test:
	@echo "Running integration and unit tests..."
	uv run pytest

lint:
	uv run --extra lint ruff check expense_agent tests
	uv run --extra lint ruff format --check expense_agent tests

serve:
	@echo "Starting ambient event listener..."
	uv run uvicorn expense_agent.main:app --host 0.0.0.0 --port 8080

generate-traces:
	@echo "Generating eval traces..."
	PYTHONPATH=. uv run python tests/eval/generate_traces.py

grade:
	@echo "Grading eval traces..."
	PYTHONPATH=. uv run python tests/eval/grade_traces.py

eval: generate-traces
	$(MAKE) grade

eval-offline:
	PYTHONPATH=. uv run python tests/eval/generate_traces.py --offline --output artifacts/traces/offline_traces.json
	PYTHONPATH=. uv run python tests/eval/grade_traces.py --traces artifacts/traces/offline_traces.json --output artifacts/grade_results/offline_results.json
