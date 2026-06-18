# Ambient Expense Approval Agent

The Ambient Expense Approval Agent is an intelligent expense-processing workflow built on the **Google ADK 2.0** graph workflow architecture. It processes JSON expense reports and automates approvals under a specified threshold while leveraging LLMs for risk assessment on larger expenses. It also implements crucial security checkpoints for PII redaction and prompt injection defense.

## Workflow Overview

1. **Input:** An expense report arrives as a JSON event.
2. **Security Checkpoint:** The description is scanned for Social Security Numbers and Credit Card numbers, replacing them with `[REDACTED_SSN]` and `[REDACTED_CC]`. It also scans for prompt injection attempts (e.g., "ignore previous instructions"). If an injection is found, it immediately routes the expense to a human reviewer.
3. **Threshold Check:** 
   - **Under $100:** Auto-approved instantly. No LLM call is made.
   - **$100 or more:** Routed to the LLM reviewer.
4. **LLM Review (`gemini-3.1-flash-lite`):** The LLM reviews the clean expense details for risk factors. If risky, it alerts and routes to human review. If clean, it approves it.
5. **Human-In-The-Loop (HITL):** A paused node awaiting explicit human approval or rejection via the ADK playground UI.

## Setup Guide

### Prerequisites
- Python 3.10+
- `uv` package manager installed (`uv tool install google-agents-cli`)
- Google AI Studio API key or GCP credentials.

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Reefat004/Ambient_Expense_Approval_Agent.git
   cd Ambient_Expense_Approval_Agent
   ```

2. **Configure Environment:**
   Create a `.env` file in the root directory and add your API key:
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```
   *(Note: The `.env` file is ignored by git to protect your credentials.)*

3. **Install Dependencies:**
   Run the following command to install required dependencies using `uv`:
   ```bash
   make install
   ```

### Running Locally

1. **Launch the ADK Playground:**
   ```bash
   make playground
   ```
   This will start the local server. You can view it in your browser (typically at http://localhost:8080).
   
2. **Testing the Agent:**
   Use the playground UI to send a test payload. Make sure your user ID matches if you're simulating different users.

   **Example Payload:**
   ```json
   {"amount": 150.0, "submitter": "alice@company.com", "category": "software", "description": "IDE License", "date": "2026-06-06"}
   ```

3. **Running Tests:**
   The project includes a suite of unit and integration tests.
   ```bash
   make test
   ```

## Project Structure
- `expense_agent/agent.py`: The core ADK graph workflow definition and nodes.
- `tests/`: Unit and integration tests covering standard routing and security checkpoints.
- `Makefile`: Commands for installation, testing, and running the playground.
- `pyproject.toml`: Project dependencies and metadata.
