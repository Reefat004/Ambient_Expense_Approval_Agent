import json
from pathlib import Path

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from expense_agent.agent import app as adk_app


def generate():
    dataset_path = Path("tests/eval/datasets/basic-dataset.json")
    out_dir = Path("artifacts/traces")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "generated_traces.json"

    with open(dataset_path) as f:
        dataset = json.load(f)

    session_service = InMemorySessionService()
    runner = Runner(
        agent=adk_app.root_agent, session_service=session_service, app_name=adk_app.name
    )

    graded_cases = []

    for case in dataset["eval_cases"]:
        case_id = case["eval_case_id"]
        print(f"Running scenario: {case_id}")
        prompt = case["prompt"]

        session = session_service.create_session_sync(
            user_id="eval_user", app_name=adk_app.name
        )

        parts = []
        for p in prompt["parts"]:
            if "text" in p:
                parts.append(types.Part.from_text(text=p["text"]))

        start_message = types.Content(role=prompt.get("role", "user"), parts=parts)

        # Run first pass
        events = list(
            runner.run(
                new_message=start_message,
                user_id="eval_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )

        # Check if paused for HITL
        decision = None
        interrupt_id = None
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if (
                        getattr(part, "function_call", None)
                        and part.function_call.name == "adk_request_input"
                    ):
                        msg = part.function_call.args.get("message", "")
                        decision = "reject" if "SECURITY ALERT" in msg else "approve"
                        interrupt_id = part.function_call.id

        if decision and interrupt_id:
            print(f" -> Intercepted RequestInput, automating decision: {decision}")
            decision_message = types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            name="adk_request_input",
                            response={"decision": decision},
                            id=interrupt_id,
                        )
                    )
                ],
            )
            list(
                runner.run(
                    new_message=decision_message,
                    user_id="eval_user",
                    session_id=session.id,
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                )
            )

        # Serialize trace
        session_final = session_service.get_session_sync(
            user_id="eval_user", app_name=adk_app.name, session_id=session.id
        )
        session_dict = session_final.model_dump(mode="json", exclude_none=True)

        clean_events = []
        for e in session_dict.get("events", []):
            if e.get("content"):
                clean_events.append(
                    {"author": e.get("author", "unknown"), "content": e.get("content")}
                )

        case["agent_data"] = {
            "agents": {adk_app.name: {"agent_id": adk_app.name}},
            "turns": [{"turn_index": 0, "events": clean_events}],
        }
        graded_cases.append(case)

    with open(out_path, "w") as f:
        json.dump({"eval_cases": graded_cases}, f, indent=2)

    print(
        f"\nSuccessfully generated traces for {len(graded_cases)} cases into {out_path}"
    )


if __name__ == "__main__":
    generate()
