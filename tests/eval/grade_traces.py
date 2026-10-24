"""Deterministic business-rule and privacy grading; no LLM judge or audit claims."""

import argparse
import json
from pathlib import Path

from expense_agent.security import CARD, SSN, normalize


def contains_identifier(value):
    if isinstance(value, str):
        return bool(SSN.search(normalize(value)) or CARD.search(normalize(value)))
    if isinstance(value, dict):
        return any(contains_identifier(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_identifier(v) for v in value)
    return False


def message_data(content):
    """Inspect message data without treating generated call IDs as employee PII."""
    values = []
    for part in content.get("parts", []):
        call = part.get("function_call", {})
        args = call.get("args", {})
        if call.get("name") == "adk_request_input":
            # ADK also repeats its generated UUID inside args.interruptId.
            # Inspect the human-visible message and full expense payload;
            # retain full argument inspection for application/model tools.
            args = {key: value for key, value in args.items() if key != "interruptId"}
        values.append(
            [part.get("text"), args, part.get("function_response", {}).get("response")]
        )
    return values


def grade_case(case):
    if case.get("generation_error"):
        return {
            "eval_case_id": case["eval_case_id"],
            "passed": False,
            "checks": {"inference_completed": False},
            "error": case["generation_error"],
        }
    expected = case["expected"]
    events = case["events"]
    calls = [
        p["function_call"]
        for e in events
        for p in e.get("content", {}).get("parts", [])
        if p.get("function_call", {}).get("name") == "adk_request_input"
    ]
    statuses = [
        e["output"]["status"]
        for e in events
        if isinstance(e.get("output"), dict) and "status" in e["output"]
    ]
    checks = {
        "model_routing": bool(case["model_requests"]) == expected["model_called"],
        "human_routing": bool(calls) == expected["review_required"],
        "final_status": bool(statuses) and statuses[-1] == expected["status"],
        "no_premature_approval": not expected["review_required"]
        or (
            "approved" not in statuses[:-1]
            and (expected["status"] == "approved" or "approved" not in statuses)
        ),
        "security_alert": not expected.get("security_alert")
        or any("SECURITY ALERT" in c.get("args", {}).get("message", "") for c in calls),
        "model_privacy": case["privacy_checks"].get("model_requests") is True,
        "session_privacy": case["privacy_checks"].get("session") is True,
        "log_privacy": case["privacy_checks"].get("logs") is True,
        "observed_model_contents_clean": not any(
            contains_identifier(message_data(content))
            for request in case["model_requests"]
            for content in request.get("contents", [])
        ),
        "observed_session_contents_clean": not any(
            contains_identifier(message_data(event.get("content", {})))
            or contains_identifier(event.get("output", {}))
            for event in case["session"].get("events", [])
        )
        and not contains_identifier(
            case["session"].get("state", {}).get("expense_data", {})
        ),
    }
    return {
        "eval_case_id": case["eval_case_id"],
        "passed": all(checks.values()),
        "checks": checks,
    }


def grade(args):
    traces = json.loads(Path(args.traces).read_text())
    results = [grade_case(case) for case in traces["eval_cases"]]
    output = {
        "run_id": traces["run_id"],
        "inference_mode": traces["inference_mode"],
        "grading_method": "deterministic_boundary_and_business_rules",
        "independent_security_audit": False,
        "passed": sum(r["passed"] for r in results),
        "total": len(results),
        "results": results,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2))
    path.with_name(f"{path.stem}_{traces['run_id']}{path.suffix}").write_bytes(
        path.read_bytes()
    )
    for result in results:
        print(f"{result['eval_case_id']}: {'PASS' if result['passed'] else 'FAIL'}")
    print(
        f"{output['passed']}/{output['total']} passed ({output['inference_mode']}, deterministic grading)"
    )
    return int(output["passed"] != output["total"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", default="artifacts/traces/generated_traces.json")
    parser.add_argument("--output", default="artifacts/grade_results/results.json")
    raise SystemExit(grade(parser.parse_args()))
