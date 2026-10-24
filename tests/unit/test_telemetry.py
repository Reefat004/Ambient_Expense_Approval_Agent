import pytest

from expense_agent.app_utils.telemetry import setup_telemetry


@pytest.mark.parametrize("bucket", [None, "logs-test"])
@pytest.mark.parametrize("capture", ["true", "false", "NO_CONTENT"])
def test_telemetry_never_enables_content(monkeypatch, bucket, capture):
    if bucket:
        monkeypatch.setenv("LOGS_BUCKET_NAME", bucket)
    else:
        monkeypatch.delenv("LOGS_BUCKET_NAME", raising=False)
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", capture)
    setup_telemetry()
    import os

    assert (
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "NO_CONTENT"
    )
