# Project Requirements Document (PRD)

## Product Name
Ambient Expense Approval Agent

## Objective
To build an automated, ambient expense-approval agent using the ADK 2.0 graph workflow. The agent processes incoming expense reports (in JSON format) and intelligently routes them based on amount and risk analysis, while incorporating strict security controls to protect PII and defend against prompt injections.

## Key Features & Requirements

1. **Graph Workflow Architecture (ADK 2.0)**
   - Utilize the new ADK 2.0 graph Workflow API, defining function nodes and edges.
   - Support a human-in-the-loop (HITL) step using `RequestInput` for paused approvals.

2. **Expense Routing Logic**
   - **Threshold-based Routing:** Expenses under $100 are automatically approved instantly without involving the LLM.
   - **LLM Review:** Expenses $100 or more are routed to an LLM (`gemini-3.1-flash-lite`) to be reviewed for risk factors. The model determines whether to raise an alert.
   - **Human Review:** If the LLM flags an expense, the workflow pauses, prompting a human to approve or reject the request.

3. **Security & Data Privacy (Security Checkpoint)**
   - **PII Scrubbing:** The description must be scrubbed of Social Security Numbers (SSNs) and credit-card numbers before the data reaches the LLM or logs.
   - **Prompt Injection Defense:** Defend against inputs designed to force auto-approval or bypass rules. Any detected injection attempt must bypass the LLM and route directly to a human for review, flagged as a security event.

4. **Testing & Observability**
   - Provide unit and integration tests mimicking the graph workflow and security behaviors.
   - Support a local `Makefile` for installing dependencies, running tests, and launching the playground UI.
   - Mock internal dependencies (like `google.genai` SDK) for reliable offline testing.

## Non-Functional Requirements
- **Technology Stack:** Python, ADK 2.0 (`google-adk>=2.0.0a0`), Google Gemini models.
- **Maintainability:** Threshold values and model configurations must be kept out of the core logic and maintained in configuration or environment variables.
- **Security:** Ensure API keys and sensitive environment variables are strictly blocked from version control using `.gitignore`.
