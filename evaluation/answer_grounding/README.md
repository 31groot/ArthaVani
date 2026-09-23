# Answer grounding evaluation — fixed v2

This evaluator is designed for volatile finance data and deliberately does not keep a frozen portfolio snapshot or rely on an LLM judge that can return malformed JSON.

## What changed

- Ground truth for live data comes from the actual tool result captured during the same run.
- PostgreSQL checkpointing is explicitly disabled so every case is independent.
- Tool routing and tool arguments remain separate from answer grounding.
- Grounding checks are deterministic and data-driven for the 20 cases.
- The evaluator no longer counts a judge-parser failure as a grounding failure.
- Every result records the live tool payload used as ground truth.
- A grounding error is distinct from a runtime/model/API error.

## Install

Replace the existing `evaluation/answer_grounding` directory with this directory.

From the repository root:

```bash
rm -rf evaluation/answer_grounding
cp -R /path/to/fixed/evaluation/answer_grounding evaluation/
```

Or copy the two source files and JSON file into the existing directory.

## Run

```bash
python -m evaluation.answer_grounding.run_answer_grounding
```

The default delay is 20 seconds between cases. To change it:

```bash
ANSWER_EVAL_DELAY_SECONDS=5 python -m evaluation.answer_grounding.run_answer_grounding
```

## Interpretation

`Tool calling accuracy` checks the expected tool names and configured arguments.

`Grounding accuracy` checks whether required facts in each answer are supported by the live tool result from that same run.

`Both criteria pass` is the strict combined metric.

For live portfolio, market price, HHI, news, NAV, FX and market-status cases, there is no frozen numeric ground truth. Tomorrow's tool output can differ and the benchmark remains valid.


## Focused reruns

Set `ANSWER_EVAL_CASE_IDS` to a comma-separated list to rerun only selected cases. For example:

```bash
ANSWER_EVAL_CASE_IDS=AG-08,AG-15 ANSWER_EVAL_CASE_DELAY_SECONDS=0 python -m evaluation.answer_grounding.run_answer_grounding
```

Numeric grounding accepts normal voice-agent rounding when the spoken or numeric value remains within the case tolerance. Materially different values still fail.


### v5 change
Grounding checks now distinguish requested facts from optional contextual facts. AG-08 only requires DATAPATTNS profit/loss and P&L percentage, because the question asks how the holding is performing; current price and average purchase price are not required facts for that question. This avoids treating a concise, grounded answer as wrong merely because it omitted extra context.


### v6 change
AG-08 now checks the requested performance facts rather than optional contextual prices. The P&L percentage allows 0.10 percentage points of tolerance for natural voice rounding.
