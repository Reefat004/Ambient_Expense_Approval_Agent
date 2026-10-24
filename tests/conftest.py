"""Network-free fixtures; model behavior belongs in the live evaluation suite."""

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field


class RecordingModel(BaseLlm):
    model: str = "offline-test-model"
    requests: list = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream=False):
        self.requests.append(llm_request.model_dump(mode="json", exclude_none=True))
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="Recommendation: approve. Human decision required."
                    )
                ],
            )
        )


@pytest.fixture(autouse=True)
def offline_services(monkeypatch):
    from unittest.mock import MagicMock

    import google.auth
    import google.cloud.logging

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "True")
    monkeypatch.setattr(
        google.auth, "default", lambda *a, **k: (MagicMock(), "dummy-project")
    )
    monkeypatch.setattr(google.cloud.logging, "Client", MagicMock)
    from google.adk.models.google_llm import Gemini

    model = RecordingModel()

    async def generate(self, llm_request, stream=False):
        async for response in model.generate_content_async(llm_request, stream):
            yield response

    monkeypatch.setattr(Gemini, "generate_content_async", generate)
    return model
