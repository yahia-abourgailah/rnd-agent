"""Eval harness for the chatbot agent. Run before and after every prompt change.

    ENV_FILE=.env.dev python evals/run.py

Needs a populated database and a reachable model endpoint — it exercises the
real graph, because the failures worth catching (ignoring canonical_id,
reporting a group's value as a total) only appear against real data.

Cases live in evals/cases.jsonl. Each records why it exists, so a future reader
knows what breaks if it is deleted.
"""

import json
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from chatbot_agent.graph import build_graph

CASES = pathlib.Path(__file__).parent / "cases.jsonl"
MAX_STEPS = 12
TARGET_CASE_COUNT = 20


def load() -> list[dict]:
    with CASES.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _comparable(text: str) -> str:
    """Lowercased, with digit grouping removed.

    The model writes "1,976" where the expected value is "1976"; that is a
    formatting choice, not a wrong answer, and the harness must not fail it.
    """
    return re.sub(r"(?<=\d),(?=\d)", "", text.lower())


def check(case: dict, output: str, tools_called: list[str]) -> list[str]:
    failures = []
    expect = case["expect"]
    haystack = _comparable(output)
    for needle in expect.get("contains", []):
        if _comparable(needle) not in haystack:
            failures.append(f"missing {needle!r}")
    for alternatives in expect.get("contains_any", []):
        # One fact, several correct phrasings: "0 projects" and "no projects"
        # are the same answer, and a case that accepts only one is testing
        # wording rather than correctness.
        if not any(_comparable(option) in haystack for option in alternatives):
            failures.append(f"none of {alternatives!r}")
    for needle in expect.get("not_contains", []):
        if _comparable(needle) in haystack:
            failures.append(f"should not contain {needle!r}")
    for tool_name in expect.get("tools", []):
        if tool_name not in tools_called:
            failures.append(f"tool not called: {tool_name}")
    return failures


def run_one(graph, case: dict) -> tuple[str, list[str], str]:
    config = {
        "configurable": {"thread_id": f"eval-{case['id']}-{uuid.uuid4()}"},
        "recursion_limit": MAX_STEPS,
    }
    result = graph.invoke(
        {"messages": [HumanMessage(content=case["input"]["message"])]}, config=config
    )
    messages = result["messages"]
    tools_called = [
        call["name"]
        for message in messages
        if isinstance(message, AIMessage)
        for call in (message.tool_calls or [])
    ]
    tool_results = [m for m in messages if isinstance(m, ToolMessage)]
    stop_reason = "complete" if tool_results or tools_called else "no_tool_call"
    return messages[-1].content, tools_called, stop_reason


def main() -> None:
    cases = load()
    passed, failed = 0, []

    graph = build_graph()
    for case in cases:
        try:
            output, tools_called, stop_reason = run_one(graph, case)
        except Exception as exc:  # noqa: BLE001 - one bad case must not abort the run
            failed.append((case["id"], [f"raised: {type(exc).__name__}: {exc}"], "error", ""))
            continue
        failures = check(case, output, tools_called)
        if failures:
            failed.append((case["id"], failures, stop_reason, output))
        else:
            passed += 1

    print(f"\n{passed}/{len(cases)} passed\n")
    for case_id, failures, stop_reason, output in failed:
        print(f"FAIL {case_id}  stop_reason={stop_reason}")
        for failure in failures:
            print(f"     {failure}")
        if output:
            print(f"     got: {output[:200]}")
        print()

    if len(cases) < TARGET_CASE_COUNT:
        print(f"NOTE: {len(cases)} cases. Target is {TARGET_CASE_COUNT} before trusting this.")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
