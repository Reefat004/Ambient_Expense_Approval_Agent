# Makefile for Ambient Expense Agent

.PHONY: install playground test lint serve generate-traces grade

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
	@echo "Running code quality checks..."
	agents-cli lint

serve:
	@echo "Starting ambient event listener..."
	uv run uvicorn expense_agent.main:app --host 0.0.0.0 --port 8080

generate-traces:
	@echo "Generating eval traces..."
	uv run python tests/eval/generate_traces.py

grade:
	@echo "Grading eval traces..."
	uv run python tests/eval/grade_traces.py
