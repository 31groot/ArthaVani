from __future__ import annotations

import asyncio
import json
import math
import os
import re
import unicodedata
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from finance_agent.errors import LLMProviderError
from finance_agent.runner import FinanceAgentRunner


BASE_DIR = Path(__file__).resolve().parents[2]
CASES_FILE = Path(__file__).resolve().with_name("answer_grounding.json")
RESULTS_FILE = Path(__file__).resolve().parent / "results" / "answer_grounding_results.json"

CASE_IDS = {
    item.strip()
    for item in os.getenv("ANSWER_EVAL_CASE_IDS", "").split(",")
    if item.strip()
}

# Accept both the original delay variable and the more explicit case-delay
# name used by the focused rerun examples. The latter takes precedence.
CASE_DELAY_SECONDS = float(
    os.getenv(
        "ANSWER_EVAL_CASE_DELAY_SECONDS",
        os.getenv("ANSWER_EVAL_DELAY_SECONDS", "20"),
    )
)
MAX_RETRIES = int(os.getenv("ANSWER_EVAL_MAX_RETRIES", "3"))


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = text.replace("‑", "-").replace("–", "-").replace("—", "-")
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[-_/]+", " ", text)
    text = re.sub(r"[^a-z0-9.%+\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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


def parse_tool_content(content: Any) -> Any:
    if isinstance(content, (dict, list, int, float, bool)) or content is None:
        return content
    text = extract_text(content).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def safe_json(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [safe_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): safe_json(v) for k, v in value.items()}
    return str(value)


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
    return bool(
        classes
        & {
            "RateLimitError",
            "APIConnectionError",
            "ConnectError",
            "ReadTimeout",
            "ConnectTimeout",
            "RemoteProtocolError",
        }
    )


def retry_delay(exc: BaseException, attempt: int) -> float:
    message = " ".join(str(item) for item in exception_chain(exc))
    match = re.search(r"try again in ([0-9.]+)s", message, re.IGNORECASE)
    if match:
        return max(float(match.group(1)) + 0.5, 2.0)
    return float(2**attempt)


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
    query: str,
    *,
    allow_retry: bool = True,
) -> dict[str, Any]:
    if runner._graph is None:
        raise RuntimeError("Finance agent graph is not started.")

    attempts = 0
    while True:
        try:
            # Answer-grounding evaluation is intentionally stateless.
            # No Postgres checkpoint is used, so every case is independent.
            return await runner._graph.ainvoke(
                {"messages": [{"role": "user", "content": query}]}
            )
        except Exception as exc:
            attempts += 1
            if not allow_retry or not is_retryable(exc) or attempts > MAX_RETRIES:
                raise
            delay = retry_delay(exc, attempts)
            print(
                f"      retry {attempts}/{MAX_RETRIES} after {delay:.1f}s "
                f"({classify_exception(exc)})"
            )
            await asyncio.sleep(delay)


def collect_execution(result: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []

    for message in result.get("messages", []):
        calls = getattr(message, "tool_calls", None) or []
        for call in calls:
            tool_calls.append(
                {
                    "name": call.get("name"),
                    "args": safe_json(call.get("args", {})),
                    "id": call.get("id"),
                }
            )

        if isinstance(message, ToolMessage):
            tool_results.append(
                {
                    "tool_name": getattr(message, "name", None),
                    "tool_call_id": getattr(message, "tool_call_id", None),
                    "content": safe_json(parse_tool_content(message.content)),
                }
            )

    final_answer = ""
    for message in reversed(result.get("messages", [])):
        if isinstance(message, (AIMessage, AIMessageChunk)):
            if getattr(message, "tool_calls", None):
                continue
            text = extract_text(getattr(message, "content", None)).strip()
            if text:
                final_answer = text
                break

    return tool_calls, tool_results, final_answer


def tools_match(expected: list[str], actual: list[str], mode: str) -> bool:
    if mode == "sequence":
        return actual == expected
    return Counter(actual) == Counter(expected)


def args_match(call: dict[str, Any], case: dict[str, Any]) -> tuple[bool, str | None]:
    expected_exact = case.get("expected_args") or {}
    expected_contains = case.get("expected_args_contains") or {}
    actual = call.get("args") or {}

    for key, expected in expected_exact.items():
        value = actual.get(key)
        if isinstance(expected, (int, float)) and isinstance(value, (int, float)):
            if not math.isclose(float(value), float(expected), rel_tol=0, abs_tol=0.000001):
                return False, f"argument {key} expected {expected!r}, got {value!r}"
        elif str(value).upper() != str(expected).upper():
            return False, f"argument {key} expected {expected!r}, got {value!r}"

    for key, expected in expected_contains.items():
        value = actual.get(key)
        if str(expected).lower() not in str(value or "").lower():
            return False, f"argument {key} expected to contain {expected!r}, got {value!r}"

    return True, None


def get_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(path)
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def find_list_item(payload: Any, path: str, match: dict[str, Any]) -> dict[str, Any] | None:
    rows = get_path(payload, path)
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and all(str(row.get(k)).upper() == str(v).upper() for k, v in match.items()):
            return row
    return None


ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen",
]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def integer_words(value: int) -> str:
    if value < 0:
        return "negative " + integer_words(-value)
    if value < 20:
        return ONES[value]
    if value < 100:
        return TENS[value // 10] + (f" {ONES[value % 10]}" if value % 10 else "")
    if value < 1000:
        return f"{ONES[value // 100]} hundred" + (f" {integer_words(value % 100)}" if value % 100 else "")
    if value < 1_000_000:
        return f"{integer_words(value // 1000)} thousand" + (f" {integer_words(value % 1000)}" if value % 1000 else "")
    if value < 1_000_000_000:
        return f"{integer_words(value // 1_000_000)} million" + (f" {integer_words(value % 1_000_000)}" if value % 1_000_000 else "")
    return str(value)


def number_spoken_variants(value: float | int, decimals: int | None = None) -> set[str]:
    number = float(value)
    negative = number < 0
    absolute = abs(number)
    if decimals is None:
        decimals = max(0, min(6, len(f"{absolute:.6f}".rstrip("0").split(".")[-1]) if "." in f"{absolute:.6f}" else 0))

    rounded = round(absolute, decimals)
    integer_part = int(rounded)
    fraction_text = ""
    if decimals:
        fraction = f"{rounded:.{decimals}f}".split(".")[1].rstrip("0")
        if fraction:
            fraction_text = " point " + " ".join(ONES[int(d)] for d in fraction)

    prefix = "negative " if negative else ""
    words = prefix + integer_words(integer_part) + fraction_text
    variants = {normalize_text(words)}
    if negative:
        variants.add(normalize_text("minus " + integer_words(integer_part) + fraction_text))
    return variants


def numeric_string_variants(value: float | int, decimals: int | None = None) -> set[str]:
    number = float(value)
    if decimals is None:
        text = str(number).rstrip("0").rstrip(".") if "." in str(number) else str(int(number))
        fixed = f"{number:.6f}".rstrip("0").rstrip(".")
    else:
        fixed = f"{number:.{decimals}f}"
        text = fixed.rstrip("0").rstrip(".")
    return {text, fixed, f"{number:,.{decimals if decimals is not None else 6}f}".rstrip("0").rstrip(".")}


def contains_number(answer: str, value: float | int, *, tolerance: float = 0.0, decimals: int | None = None) -> bool:
    normalized = normalize_text(answer)

    def matches_exact(candidate: float | int, candidate_decimals: int | None) -> bool:
        for variant in number_numeric_candidates(candidate, candidate_decimals):
            pattern = rf"(?<!\d){re.escape(normalize_text(variant))}(?!\d)"
            if re.search(pattern, normalized):
                return True
        for variant in number_spoken_variants(candidate, candidate_decimals):
            if variant and variant in normalized:
                return True
        return False

    if matches_exact(value, decimals):
        return True

    if tolerance > 0:
        # Voice agents commonly render prices/percentages to fewer decimal
        # places than the provider returns. Accept any rounded representation
        # that is numerically within the declared tolerance, including the
        # spoken-word form. This does not make materially different values pass.
        target = float(value)
        for precision in range(0, 7):
            rounded = round(target, precision)
            if abs(rounded - target) <= tolerance:
                if matches_exact(rounded, precision if precision > 0 else 0):
                    return True

        # Digit-form tolerance for user-facing phrases like "about 3,360".
        nums = []
        for match in re.finditer(r"(?<![a-z\d])[-+]?\d+(?:\.\d+)?(?![a-z\d])", normalized):
            try:
                nums.append(float(match.group(0)))
            except ValueError:
                pass
        if any(abs(n - target) <= tolerance for n in nums):
            return True

    return False


def number_numeric_candidates(value: float | int, decimals: int | None = None) -> set[str]:
    number = float(value)
    variants = set(numeric_string_variants(number, decimals))
    if number.is_integer():
        variants.add(str(int(number)))
        variants.add(f"{int(number):,}")
    return variants


def is_negative_number(value: Any) -> bool:
    try:
        return float(value) < 0
    except (TypeError, ValueError):
        return False


def render_exact_value(answer: str, value: Any, tolerance: float = 0.0) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    decimals = None
    abs_value = abs(float(value))
    if abs_value and not float(abs_value).is_integer():
        decimals = min(6, max(1, len(f"{abs_value:.6f}".rstrip("0").split(".")[1])))
    return contains_number(answer, float(value), tolerance=tolerance, decimals=decimals)


def evaluate_check(check: dict[str, Any], payload: Any, answer: str) -> tuple[bool, str]:
    kind = check["type"]
    normalized = normalize_text(answer)

    try:
        if kind == "number_path":
            value = get_path(payload, check["path"])
            ok = render_exact_value(answer, value, float(check.get("tolerance", 0.0)))
            return ok, f"{check.get('label', check['path'])}: expected {value!r}"

        if kind == "list_number":
            row = find_list_item(payload, check["path"], check["match"])
            if row is None:
                return False, f"no list item matched {check['match']}"
            value = get_path(row, check["value_path"])
            ok = render_exact_value(answer, value, float(check.get("tolerance", 0.0)))
            return ok, f"{check.get('label', check['value_path'])}: expected {value!r}"

        if kind == "allocation_number":
            rows = get_path(payload, "allocation")
            row = next((r for r in rows if isinstance(r, dict) and str(r.get("trading_symbol")).upper() == str(check["match"]["trading_symbol"]).upper()), None)
            if row is None:
                return False, f"allocation item not found: {check['match']}"
            value = get_path(row, check["value_path"])
            ok = render_exact_value(answer, value, float(check.get("tolerance", 0.0)))
            return ok, f"{check.get('label', 'allocation')}: expected {value!r}"

        if kind == "text_contains":
            values = [normalize_text(v) for v in check["values"]]
            ok = any(v in normalized for v in values)
            return ok, f"answer should contain one of {check['values']}"

        if kind == "text_contains_any":
            values = [normalize_text(v) for v in check["values"]]
            ok = any(v in normalized for v in values)
            return ok, f"answer should contain one of {check['values']}"

        if kind == "text_path_any":
            actual = normalize_text(get_path(payload, check["path"]))
            ok = any(normalize_text(v) == actual or normalize_text(v) in actual for v in check["values"])
            return ok, f"{check['path']}: expected one of {check['values']}, got {actual!r}"

        if kind == "text_equals_path":
            value = get_path(payload, check["path"])
            actual = normalize_text(value)
            # Accept the canonical value, plus normalised natural-language mentions.
            ok = bool(actual) and (actual in normalized or normalized.find(actual) >= 0)
            return ok, f"{check.get('label', check['path'])}: expected mention of {value!r}"

        if kind == "boolean_text":
            value = bool(get_path(payload, check["path"]))
            if value:
                accepted = ["yes", "open", "true", "is open", "currently open"]
            else:
                accepted = ["no", "not open", "closed", "false", "outside", "not currently open"]
            ok = any(token in normalized for token in accepted)
            return ok, f"{check['path']}: expected {value}"

        if kind == "sentiment":
            value = get_path(payload, check["path"])
            if is_negative_number(value):
                ok = any(token in normalized for token in [normalize_text(w) for w in check.get("negative_words", [])])
                return ok, f"negative value should be described as a loss/down/negative result"
            return True, "positive/non-negative value needs no negative sentiment check"

        if kind == "amfi_latest_result":
            rows = payload.get("results", []) if isinstance(payload, dict) else []
            if not rows:
                return False, "AMFI returned no matching result"
            name_contains = normalize_text(check.get("name_contains", ""))
            row = next((r for r in rows if name_contains in normalize_text(r.get("scheme_name", ""))), rows[0])
            answer_ok = (
                render_exact_value(answer, row.get("nav"), 0.01)
                and name_contains in normalized
            )
            return answer_ok, f"AMFI expected {row.get('scheme_name')} NAV {row.get('nav')} dated {row.get('date')}"

        if kind == "news_support":
            rows = payload if isinstance(payload, list) else []
            if not rows:
                return False, "news tool returned no articles"
            # The answer must ground itself in at least one returned item by
            # mentioning either its publisher or a short phrase from its title.
            for row in rows:
                if not isinstance(row, dict):
                    continue
                publisher = normalize_text(row.get("publisher", ""))
                if publisher and len(publisher) >= 4 and publisher in normalized:
                    return True, f"news answer cites returned publisher {publisher!r}"
                title_words = normalize_text(row.get("title", "")).split()
                if len(title_words) >= 5:
                    fingerprint = " ".join(title_words[:5])
                    if fingerprint in normalized:
                        return True, f"news answer contains returned headline fingerprint {fingerprint!r}"
            return False, "answer did not mention a returned news publisher or headline fingerprint"

        if kind == "market_status_text":
            is_open = bool(get_path(payload, check["path"]))
            if is_open:
                accepted = ["open", "currently open"]
                rejected = ["closed", "not open"]
            else:
                accepted = ["closed", "not open", "not currently open", "outside regular session", "market is shut"]
                rejected = ["open now", "currently open"]
            has_accepted = any(token in normalized for token in accepted)
            has_rejected = any(token in normalized for token in rejected)
            ok = has_accepted and not (is_open and has_rejected) and not ((not is_open) and ("open now" in normalized or "currently open" in normalized))
            return ok, f"NSE open={is_open}"

        if kind == "largest_loss_holding":
            rows = payload.get("holdings", []) if isinstance(payload, dict) else []
            loss_rows = []
            for row in rows:
                try:
                    pnl = float(row.get("profit_loss"))
                except (TypeError, ValueError):
                    continue
                if pnl < 0:
                    loss_rows.append((pnl, row))
            if not loss_rows:
                return False, "no negative holding P&L was available"
            pnl, row = min(loss_rows, key=lambda item: item[0])
            symbol = normalize_text(row.get("trading_symbol"))
            value_ok = render_exact_value(answer, abs(pnl), float(check.get("tolerance", 1.0)))
            symbol_ok = symbol in normalized
            loss_words_ok = any(word in normalized for word in ["loss", "down", "negative", "worst", "biggest"])
            return value_ok and symbol_ok and loss_words_ok, f"largest loss should be {row.get('trading_symbol')} at {pnl}"

        raise ValueError(f"Unknown grounding check type: {kind}")
    except (KeyError, TypeError, ValueError) as exc:
        return False, f"check failed: {exc}"


def evaluate_grounding(case: dict[str, Any], answer: str, tool_results: list[dict[str, Any]]) -> dict[str, Any]:
    spec = case.get("grounding") or {}
    expected_tool = spec.get("tool")
    candidate_results = [r for r in tool_results if r.get("tool_name") == expected_tool]
    if not candidate_results:
        return {
            "status": "FAIL",
            "checks": [],
            "failures": [f"no tool result captured for {expected_tool}"],
            "ground_truth_source": "runtime_tool_result",
        }

    payload = candidate_results[-1].get("content")
    checks_out = []
    failures = []
    for check in spec.get("checks", []):
        ok, reason = evaluate_check(check, payload, answer)
        checks_out.append({"type": check["type"], "passed": ok, "detail": reason})
        if not ok:
            failures.append(reason)

    status = "PASS" if not failures else "FAIL"
    return {
        "status": status,
        "checks": checks_out,
        "failures": failures,
        "ground_truth_source": "runtime_tool_result",
        "ground_truth_tool": expected_tool,
        "ground_truth": safe_json(payload),
    }


async def run_case(runner: FinanceAgentRunner, case: dict[str, Any]) -> dict[str, Any]:
    result = await invoke_turn(runner, case["query"])
    tool_calls, tool_results, final_answer = collect_execution(result)

    expected_tools = list(case.get("expected_tools", []))
    actual_tools = [call["name"] for call in tool_calls]
    tool_ok = tools_match(expected_tools, actual_tools, case.get("tool_match", "set"))

    arg_failures = []
    for expected_name in expected_tools:
        matching = [call for call in tool_calls if call["name"] == expected_name]
        if not matching:
            continue
        ok, reason = args_match(matching[-1], case)
        if not ok and reason:
            arg_failures.append(reason)
    if arg_failures:
        tool_ok = False

    tool_result_payloads = [r for r in tool_results]
    grounding = evaluate_grounding(case, final_answer, tool_result_payloads)
    overall = tool_ok and grounding["status"] == "PASS"

    return {
        "id": case["id"],
        "query": case["query"],
        "expected_tools": expected_tools,
        "actual_tools": actual_tools,
        "tool_calls": tool_calls,
        "tool_selection_correct": tool_ok,
        "tool_argument_failures": arg_failures,
        "final_answer": final_answer,
        "grounding": grounding,
        "grounding_correct": grounding["status"] == "PASS",
        "overall": "PASS" if overall else "FAIL",
    }


async def main() -> None:
    with CASES_FILE.open("r", encoding="utf-8") as f:
        cases = json.load(f)

    if CASE_IDS:
        cases = [case for case in cases if case.get("id") in CASE_IDS]
        if not cases:
            raise SystemExit(f"No benchmark cases matched ANSWER_EVAL_CASE_IDS={sorted(CASE_IDS)!r}")

    # Explicitly disable Postgres for this suite. Memory is not being measured here.
    runner = FinanceAgentRunner(database_url="")
    results: list[dict[str, Any]] = []

    try:
        await runner.start()

        for index, case in enumerate(cases, start=1):
            print(f"[{index:02d}/{len(cases):02d}] {case['id']}: ", end="", flush=True)
            try:
                result = await run_case(runner, case)
                results.append(result)
                print(
                    f"TOOL={'PASS' if result['tool_selection_correct'] else 'FAIL'} "
                    f"GROUNDING={'PASS' if result['grounding_correct'] else 'FAIL'} "
                    f"OVERALL={result['overall']}"
                )
                if result["grounding"]["failures"]:
                    for failure in result["grounding"]["failures"]:
                        print(f"      grounding: {failure}")
                if result["tool_argument_failures"]:
                    for failure in result["tool_argument_failures"]:
                        print(f"      args: {failure}")
            except Exception as exc:
                result = {
                    "id": case["id"],
                    "query": case["query"],
                    "status": "ERROR",
                    "error_kind": classify_exception(exc),
                    "error_type": type(exc).__name__,
                    "error_classes": sorted(error_classes(exc)),
                    "error": str(exc),
                }
                results.append(result)
                print(f"ERROR [{result['error_kind']}]: {exc}")

            if index < len(cases):
                print(f"      waiting {CASE_DELAY_SECONDS:.0f}s...")
                await asyncio.sleep(CASE_DELAY_SECONDS)
    finally:
        await runner.stop()

    passed = [r for r in results if r.get("overall") == "PASS"]
    valid = [r for r in results if r.get("status") != "ERROR"]
    tool_pass = [r for r in valid if r.get("tool_selection_correct")]
    grounding_pass = [r for r in valid if r.get("grounding_correct")]
    errors = [r for r in results if r.get("status") == "ERROR"]

    total_valid = len(valid)
    summary = {
        "benchmark": "ArthaVani Answer Grounding + Tool Calling",
        "version": 3,
        "ground_truth_mode": "runtime_tool_result",
        "llm_grounding_judge": False,
        "memory_enabled": False,
        "total_cases": len(results),
        "valid_cases": total_valid,
        "errors": len(errors),
        "tool_calling_accuracy_percent": round((len(tool_pass) / total_valid) * 100, 2) if total_valid else 0.0,
        "grounding_accuracy_percent": round((len(grounding_pass) / total_valid) * 100, 2) if total_valid else 0.0,
        "both_criteria_pass_percent": round((len(passed) / total_valid) * 100, 2) if total_valid else 0.0,
        "passed_both": len(passed),
        "grounding_definition": "Every required factual check must be supported by the live tool result captured during the same run.",
        "case_delay_seconds": CASE_DELAY_SECONDS,
    }

    output = {"summary": summary, "results": results}
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("\n=== Answer Grounding + Tool Calling ===")
    print(f"Total cases:              {summary['total_cases']}")
    print(f"Valid cases:              {summary['valid_cases']}")
    print(f"Tool calling accuracy:    {summary['tool_calling_accuracy_percent']:.2f}%")
    print(f"Grounding accuracy:       {summary['grounding_accuracy_percent']:.2f}%")
    print(f"Both criteria pass:       {summary['both_criteria_pass_percent']:.2f}%")
    print(f"Errors:                   {summary['errors']}")
    print(f"Results: {RESULTS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
