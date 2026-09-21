import asyncio
import sys
from pathlib import Path

# Ensure the project root (parent of this tests/ directory) is on
# sys.path, so `finance_agent` and other top-level packages import
# correctly regardless of the working directory this script is run
# from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finance_agent.runner import FinanceAgentRunner


async def main():
    question = " ".join(sys.argv[1:]) or "What's my checking account balance?"

    print(f"Question: {question!r}")
    print("Starting finance agent (this spawns the MCP server subprocess "
          "and calls Groq)...")

    runner = FinanceAgentRunner()

    try:
        chunks = []
        async for chunk in runner.astream_text(
            [{"role": "user", "content": question}]
        ):
            print(f"[chunk] {chunk!r}")
            chunks.append(chunk)

        full_text = "".join(chunks)
        print()
        print(f"FULL RESPONSE: {full_text!r}")

        if not full_text.strip():
            print("\n*** FAILURE: response was empty. ***")
        else:
            print("\n*** SUCCESS ***")

    except Exception:
        print("\n*** FAILURE: an exception was raised. ***")
        raise

    finally:
        await runner.stop()


if __name__ == "__main__":
    asyncio.run(main())