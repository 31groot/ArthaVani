import asyncio

import pytest

from voice.text.text_splitter import SentenceSplitter


async def collect_sentences(chunks):
    queue = asyncio.Queue()
    splitter = SentenceSplitter(queue)

    for chunk in chunks:
        await splitter.feed(chunk)

    await splitter.flush()

    results = []

    while not queue.empty():
        event = await queue.get()
        results.append(event.text)

    return results


@pytest.mark.asyncio
async def test_decimal_not_split():
    results = await collect_sentences(
        ["Infosys is down 0.9 percent from the previous close."]
    )

    assert results == [
        "Infosys is down 0.9 percent from the previous close."
    ]


@pytest.mark.asyncio
async def test_streamed_decimal_not_split():
    results = await collect_sentences(
        [
            "Infosys is down roughly 0.",
            "9 percent from the previous close.",
        ]
    )

    assert results == [
        "Infosys is down roughly 0.9 percent from the previous close."
    ]


@pytest.mark.asyncio
async def test_multiple_decimal_values():
    results = await collect_sentences(
        [
            "Infosys is at 1029.40 rupees, down 0.9 percent. "
            "TCS is at 2105.25 rupees, down 1.1 percent."
        ]
    )

    assert results == [
        "Infosys is at 1029.40 rupees, down 0.9 percent.",
        "TCS is at 2105.25 rupees, down 1.1 percent.",
    ]


@pytest.mark.asyncio
async def test_normal_sentences_still_split():
    results = await collect_sentences(
        [
            "Hello. How are you? I am ready!"
        ]
    )

    assert results == [
        "Hello.",
        "How are you?",
        "I am ready!",
    ]


@pytest.mark.asyncio
async def test_currency_decimal():
    results = await collect_sentences(
        [
            "The share price is ₹1029.40. "
            "That is up 12.5 rupees today."
        ]
    )

    assert results == [
        "The share price is ₹1029.40.",
        "That is up 12.5 rupees today.",
    ]
