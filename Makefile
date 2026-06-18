# Makefile for Ambient Expense Agent

.PHONY: install playground test lint

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
