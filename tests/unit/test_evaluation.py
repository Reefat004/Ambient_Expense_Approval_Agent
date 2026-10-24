"""The evaluator must reject leaked content and incorrect routes, not just score fixtures."""

import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "project_grader", Path(__file__).parents[1] / "eval/grade_traces.py"
)
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)


def clean_case():
    return {
        "eval_case_id": "fixture",
        "expected": {
            "model_called": False,
            "review_required": False,
            "status": "approved",
        },
        "events": [{"output": {"status": "approved"}}],
        "model_requests": [],
        "privacy_checks": {"model_requests": True, "session": True, "logs": True},
        "session": {"events": [], "state": {}},
    }


@pytest.mark.parametrize(
    "corruption",
    ["route", "status", "model_leak", "session_leak", "inference_error", "log_leak"],
)
def test_evaluator_fails_corrupted_evidence(corruption):
    case = copy.deepcopy(clean_case())
    assert grader.grade_case(case)["passed"] is True
    if corruption == "route":
        case["expected"]["review_required"] = True
    elif corruption == "status":
        case["events"][0]["output"]["status"] = "rejected"
    elif corruption == "model_leak":
        case["expected"]["model_called"] = True
        case["model_requests"] = [
            {"contents": [{"parts": [{"text": "SSN 123-45-6789"}]}]}
        ]
    elif corruption == "session_leak":
        case["session"]["state"]["expense_data"] = {"description": "SSN 123-45-6789"}
    elif corruption == "inference_error":
        case["generation_error"] = "TimeoutError"
    else:
        case["privacy_checks"]["logs"] = False
    assert grader.grade_case(case)["passed"] is False


@pytest.mark.parametrize("leaked_payload", [False, True])
def test_interrupt_uuid_is_metadata_but_payload_is_inspected(leaked_payload):
    case = clean_case()
    case["session"]["events"] = [
        {
            "content": {
                "parts": [
                    {
                        "function_call": {
                            "name": "adk_request_input",
                            "args": {
                                "interruptId": "c177c6ba-2725-4e13-8d7c-894891476c58",
                                "payload": {
                                    "description": "SSN 123-45-6789"
                                    if leaked_payload
                                    else "[REDACTED_SSN]"
                                },
                            },
                        }
                    }
                ]
            }
        }
    ]
    assert grader.grade_case(case)["passed"] is (not leaked_payload)
