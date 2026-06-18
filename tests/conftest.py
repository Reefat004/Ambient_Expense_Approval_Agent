# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from unittest.mock import MagicMock

import google.auth
import google.cloud.logging
import google.genai
from google.genai import types

# Pre-set dummy GCP environment variables for tests
os.environ["GOOGLE_CLOUD_PROJECT"] = "dummy-project"
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

# Mock google.auth.default
mock_credentials = MagicMock()
google.auth.default = lambda *args, **kwargs: (mock_credentials, "dummy-project")

# Mock google.cloud.logging.Client to avoid 403 API errors during tests
google.cloud.logging.Client = MagicMock

# Mock google.genai.Client to prevent live LLM API calls during tests
# Define mock response
mock_candidate = types.Candidate(
    content=types.Content(
        role="model",
        parts=[types.Part.from_text(text="Mocked LLM risk review: Low risk.")],
    )
)
mock_response = types.GenerateContentResponse(
    candidates=[mock_candidate],
)

# Original Client.__init__
original_client_init = google.genai.Client.__init__


def mocked_client_init(self, *args, **kwargs):
    original_client_init(self, *args, **kwargs)

    # Mock synchronous generation method
    self.models.generate_content = MagicMock(return_value=mock_response)

    # Mock asynchronous generation methods
    async def dummy_generate(*args, **kwargs):
        return mock_response

    async def dummy_stream(*args, **kwargs):
        async def inner_stream():
            yield mock_response

        return inner_stream()

    self.aio.models.generate_content = dummy_generate
    self.aio.models.generate_content_stream = dummy_stream


# Apply the patch
google.genai.Client.__init__ = mocked_client_init
