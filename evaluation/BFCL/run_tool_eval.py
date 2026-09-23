from __future__ import annotations

import asyncio
import json
import math
import os
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from finance_agent.errors import LLMProviderError
from finance_agent.runner import FinanceAgentRunner


BASE_DIR = Path(__file__).resolve().parent.parent
CASES_FILE = BASE_DIR / "evaluation" / "tool_eval.json"
RESULTS_FILE = BASE_DIR / "evaluation" / "results" / "tool_eval_results.json"

CASE_DELAY_SECONDS = float(os.getenv("EVAL_CASE_DELAY_SECONDS", "20"))
MAX_RETRIES = 3


def extract_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)

    return str(content)


def extract_tool_calls(result: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    for message in result.get("messages", []):
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            continue

        for call in tool_calls:
            calls.append(
                {
                    "name": call.get("name"),
                    "args": call.get("args", {}),
                    "id": call.get("id"),
                }
            )

    return calls


def extract_final_answer(result: dict[str, Any]) -> str:
    for message in reversed(result.get("messages", [])):
        text = extract_text(getattr(message, "content", None))
        if text:
            return text
    return ""


def exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc

    while current is not None:
        chain.append(current)
        current = current.__cause__ or current.__context__

    return chain


def error_classes(exc: BaseException) -> set[str]:
    return {type(item).__name__ for item in exception_chain(exc)}


def is_retryable(exc: BaseException) -> bool:
    classes = error_classes(exc)

    retryable = {
        "RateLimitError",
        "APIConnectionError",
        "ConnectError",
        "ReadTimeout",
        "ConnectTimeout",
        "RemoteProtocolError",
    }

    return bool(classes & retryable)


def retry_delay(exc: BaseException, attempt: int) -> float:
    message = " ".join(str(item) for item in exception_chain(exc))

    match = re.search(r"try again in ([0-9.]+)s", message, re.IGNORECASE)
    if match:
        return max(float(match.group(1)) + 0.5, 2.0)

    return float(2 ** attempt)


def classify_exception(exc: BaseException) -> str:
    classes = error_classes(exc)

    if "RateLimitError" in classes:
        return "RATE_LIMIT"
    if {
        "APIConnectionError",
        "ConnectError",
        "ReadTimeout",
        "ConnectTimeout",
        "RemoteProtocolError",
    } & classes:
        return "NETWORK_ERROR"
    if "BadRequestError" in classes:
        return "MODEL_API_ERROR"

    if isinstance(exc, LLMProviderError):
        return "LLM_ERROR"

    return "APPLICATION_ERROR"


async def invoke_turn(
    runner: FinanceAgentRunner,
    content: str,
    thread_id: str,
    *,
    allow_retry: bool,
) -> dict[str, Any]:
    if runner._graph is None:
        raise RuntimeError("Finance agent graph is not started.")

    attempts = 0

    while True:
        try:
            result = await runner._graph.ainvoke(
                {"messages": [{"role": "user", "content": content}]},
                config=runner._build_config(thread_id),
            )
            return result

        except Exception as exc:
            attempts += 1

            if (
                not allow_retry
                or not is_retryable(exc)
                or attempts > MAX_RETRIES
            ):
                raise

            delay = retry_delay(exc, attempts)

            print(
                f"      retry {attempts}/{MAX_RETRIES} after "
                f"{delay:.1f}s ({classify_exception(exc)})"
            )

            await asyncio.sleep(delay)


def tools_match(
    expected: list[str],
    actual: list[str],
    mode: str,
) -> bool:
    if mode == "sequence":
        return actual == expected

    return Counter(actual) == Counter(expected)


async def run_case(
    runner: FinanceAgentRunner,
    case: dict[str, Any],
) -> dict[str, Any]:
    case_id = case["id"]
    side_effect = bool(case.get("side_effect", False))
    allow_retry = not side_effect

    thread_id = f"eval-{case_id}-{uuid.uuid4().hex[:8]}"

    all_tool_calls: list[dict[str, Any]] = []
    final_answer = ""
    message_offset = 0

    turns = case.get("turns")

    if turns:
        for turn in turns:
            result = await invoke_turn(
                runner,
                turn,
                thread_id,
                allow_retry=allow_retry,
            )

            messages = result.get("messages", [])
            new_messages = messages[message_offset:]
            message_offset = len(messages)

            calls = extract_tool_calls({"messages": new_messages})
            all_tool_calls.extend(calls)

            new_answer = extract_text(
                getattr(new_messages[-1], "content", None)
            ) if new_messages else ""

            if new_answer:
                final_answer = new_answer
    else:
        result = await invoke_turn(
            runner,
            case["query"],
            thread_id,
            allow_retry=allow_retry,
        )

        all_tool_calls.extend(extract_tool_calls(result))
        final_answer = extract_final_answer(result)

    expected_tools = case.get("expected_tools", [])
    actual_tools = [call["name"] for call in all_tool_calls]

    mode = case.get("tool_match", "set")
    correct = tools_match(expected_tools, actual_tools, mode)

    return {
        "id": case_id,
        "status": "PASS" if correct else "FAIL",
        "type": case.get("type"),
        "query": case.get("query"),
        "turns": turns,
        "expected_tools": expected_tools,
        "actual_tools": actual_tools,
        "tool_calls": all_tool_calls,
        "tool_selection_correct": correct,
        "final_answer": final_answer,
    }


async def main() -> None:
    with CASES_FILE.open("r", encoding="utf-8") as f:
        cases = json.load(f)

    runner = FinanceAgentRunner()
    results: list[dict[str, Any]] = []

    try:
        await runner.start()

        for index, case in enumerate(cases, start=1):
            print(
                f"[{index:02d}/{len(cases):02d}] "
                f"{case['id']}: ",
                end="",
                flush=True,
            )

            try:
                result = await run_case(runner, case)
                results.append(result)

                if result["status"] == "PASS":
                    print("PASS")
                else:
                    print(
                        "FAIL "
                        f"(expected={result['expected_tools']}, "
                        f"actual={result['actual_tools']})"
                    )

            except Exception as exc:
                error_kind = classify_exception(exc)

                result = {
                    "id": case["id"],
                    "status": "ERROR",
                    "error_kind": error_kind,
                    "error_type": type(exc).__name__,
                    "error_classes": sorted(error_classes(exc)),
                    "error": str(exc),
                }
                results.append(result)

                print(f"ERROR [{error_kind}]: {exc}")

            if index < len(cases):
                print(
                    f"      waiting {CASE_DELAY_SECONDS:.0f}s "
                    "before next case..."
                )
                await asyncio.sleep(CASE_DELAY_SECONDS)

    finally:
        await runner.stop()

    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] == "FAIL"]
    errors = [r for r in results if r["status"] == "ERROR"]

    valid = len(passed) + len(failed)
    accuracy = (len(passed) / valid * 100) if valid else 0.0

    summary = {
        "total_cases": len(results),
        "valid_cases": valid,
        "passed": len(passed),
        "failed": len(failed),
        "errors": len(errors),
        "tool_selection_accuracy_percent": round(accuracy, 2),
        "error_breakdown": dict(
            Counter(r["error_kind"] for r in errors)
        ),
        "case_delay_seconds": CASE_DELAY_SECONDS,
    }

    output = {
        "summary": summary,
        "results": results,
    }

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with RESULTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("\n=== ArthaVani Tool Evaluation ===")
    print(f"Total cases:              {summary['total_cases']}")
    print(f"Valid cases:              {summary['valid_cases']}")
    print(f"Passed:                   {summary['passed']}")
    print(f"Failed:                   {summary['failed']}")
    print(f"Errors:                   {summary['errors']}")
    print(
        "Tool selection accuracy:  "
        f"{summary['tool_selection_accuracy_percent']:.2f}%"
    )

    if summary["error_breakdown"]:
        print(f"Error breakdown:          {summary['error_breakdown']}")

    print(f"\nDetailed results: {RESULTS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
