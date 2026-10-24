"""Run synthetic scenarios and retain sanitized boundary evidence.

Live inference is the default. --offline tests orchestration with a stub model
and is explicitly labeled; it does not establish model quality.
"""

import argparse
import asyncio
import contextlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from expense_agent.agent import app
from expense_agent.security import CARD, SSN, decode_expense, normalize


class BoundaryRecorder(BasePlugin):
    def __init__(self):
        super().__init__(name="eval_boundary_recorder")
        self.requests = []

    async def before_model_callback(self, *, callback_context, llm_request):
        self.requests.append(llm_request.model_dump(mode="json", exclude_none=True))


async def offline_generate(self, llm_request, stream=False):
    yield LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text="Offline stub recommendation: approve. Human review required."
                )
            ],
        )
    )


async def generate(args):
    dataset = json.loads(Path(args.dataset).read_text())
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results = []
    provider_failed = False
    recorder = BoundaryRecorder()
    # Privacy plugin executes first, then this recorder sees the assembled input.
    eval_app = app.model_copy(update={"plugins": [*app.plugins, recorder]})
    patch_context = (
        patch.object(Gemini, "generate_content_async", offline_generate)
        if args.offline
        else contextlib.nullcontext()
    )
    with patch_context:
        for case in dataset["eval_cases"]:
            case_id = case["eval_case_id"]
            print(f"Running: {case_id}", flush=True)
            if provider_failed:
                results.append(
                    {
                        "eval_case_id": case_id,
                        "expected": case["expected"],
                        "generation_error": "NotRunAfterProviderFailure",
                    }
                )
                continue
            recorder.requests.clear()
            service = InMemorySessionService()
            session = await service.create_session(
                app_name=app.name, user_id="synthetic_eval"
            )
            runner = Runner(app=eval_app, session_service=service)
            message = types.Content.model_validate(case["prompt"])
            stdout = io.StringIO()
            events = []
            error = None

            async def run(message, runner=runner, session_id=session.id):
                return [
                    e
                    async for e in runner.run_async(
                        new_message=message,
                        user_id="synthetic_eval",
                        session_id=session_id,
                    )
                ]

            with contextlib.redirect_stdout(stdout):
                try:
                    events = await asyncio.wait_for(run(message), timeout=45)
                    calls = [
                        p.function_call
                        for e in events
                        if e.content
                        for p in e.content.parts or []
                        if p.function_call
                        and p.function_call.name == "adk_request_input"
                    ]
                    if calls and case.get("decision"):
                        response = types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    function_response=types.FunctionResponse(
                                        name="adk_request_input",
                                        id=calls[0].id,
                                        response={"decision": case["decision"]},
                                    )
                                )
                            ],
                        )
                        events.extend(await asyncio.wait_for(run(response), timeout=45))
                except Exception as exc:
                    error = type(exc).__name__
                    provider_failed = True
            final_session = await service.get_session(
                app_name=app.name, user_id="synthetic_eval", session_id=session.id
            )
            snapshot = final_session.model_dump(mode="json", exclude_none=True)
            # Find the synthetic identifiers in the source, but never persist them
            # in generated artifacts, including the top-level prompt copy.
            source = "".join(p.get("text", "") for p in case["prompt"]["parts"])
            try:
                source = json.dumps(decode_expense(source), ensure_ascii=False)
            except (ValueError, TypeError):
                pass
            source = normalize(source)
            identifiers = {
                m.group() for pattern in (SSN, CARD) for m in pattern.finditer(source)
            }
            evidence = {
                "model_requests": recorder.requests.copy(),
                "session": snapshot,
                "logs": stdout.getvalue(),
            }
            privacy_checks = {
                name: not any(
                    value in json.dumps(data, ensure_ascii=False)
                    for value in identifiers
                )
                for name, data in evidence.items()
            }
            entry = {
                "eval_case_id": case_id,
                "expected": case["expected"],
                "privacy_checks": privacy_checks,
                "identifier_count": len(identifiers),
                "model_requests": recorder.requests.copy(),
                "session": snapshot,
                "events": [
                    e.model_dump(mode="json", exclude_none=True) for e in events
                ],
            }
            if error:
                entry["generation_error"] = error
            results.append(entry)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "inference_mode": "offline_stub" if args.offline else "live_provider",
                "source_dataset": args.dataset,
                "eval_cases": results,
            },
            indent=2,
        )
    )
    # Retain each run even if a later provider failure overwrites the latest file.
    output.with_name(f"{output.stem}_{run_id}{output.suffix}").write_bytes(
        output.read_bytes()
    )
    print(
        f"Wrote {output}; {sum('generation_error' not in r for r in results)}/{len(results)} completed",
        flush=True,
    )
    return int(any("generation_error" in r for r in results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--dataset", default="tests/eval/datasets/basic-dataset.json")
    parser.add_argument("--output", default="artifacts/traces/generated_traces.json")
    raise SystemExit(asyncio.run(generate(parser.parse_args())))
