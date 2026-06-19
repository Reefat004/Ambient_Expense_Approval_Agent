"""Centralized configuration for the ambient expense agent."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# --- Authentication ---
# If GEMINI_API_KEY is set, use AI Studio (default).
# Otherwise, fall back to Vertex AI with Google Cloud credentials.
if (
    os.getenv("GEMINI_API_KEY")
    and os.getenv("GEMINI_API_KEY") != "your_gemini_api_key_here"
):
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")
else:
    # Fallback to Vertex AI auth setup
    try:
        import google.auth

        _, project_id = google.auth.default()
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id or "dummy-project")
    except Exception:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "dummy-project")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")


@dataclass
class ExpenseAgentConfig:
    """Agent configuration with configurable threshold and model."""

    model: str = "gemini-3.1-flash-lite"
    review_threshold: float = 100.0


config = ExpenseAgentConfig()
