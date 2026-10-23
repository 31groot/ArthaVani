"""Text-level echo detection.

Even a good AEC leaves a faint copy of the assistant's voice in the
microphone. Because that copy is *clean synthetic speech*, both Silero VAD
and Deepgram happily react to it. The pipeline, however, knows exactly what
it is saying, so a transcript made of the assistant's own words is
almost certainly echo and must not trigger barge-in or become a user turn.
"""
from __future__ import annotations

import difflib
import re
import time
from collections import deque

from config.constants import ECHO_GUARD_MAX_AGE_SECONDS, ECHO_GUARD_NOVEL_RATIO

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

STOPWORDS = frozenset(
    "a an the and or of to in on at is are was it its this that for with as by".split()
)
NEUTRAL_WORDS = frozenset(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty "
    "sixty seventy eighty ninety hundred thousand lakh lakhs crore crores million "
    "billion point minus plus percent per cent rupee rupees dollar dollars".split()
)
FILLERS = frozenset("uh um umm hmm hm mm mhm ah oh huh er".split())


def tokenize(text: str) -> list[str]:
    text = text.casefold().replace("&", " and ").replace("%", " percent ")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return _TOKEN_RE.findall(text)


class EchoGuard:
    def __init__(self, *, max_age: float = ECHO_GUARD_MAX_AGE_SECONDS,
                 novel_ratio: float = ECHO_GUARD_NOVEL_RATIO) -> None:
        self.max_age = max_age
        self.novel_ratio = novel_ratio
        self._entries: deque[tuple[float, list[str]]] = deque()
        self._vocab: set[str] = set()
        self._compact = ""

    def note_spoken(self, text: str, *, now: float | None = None) -> None:
        tokens = tokenize(text)
        if not tokens:
            return
        self._entries.append((time.monotonic() if now is None else now, tokens))
        self._rebuild()

    def clear(self) -> None:
        self._entries.clear()
        self._rebuild()

    def _rebuild(self) -> None:
        self._vocab = {t for _, toks in self._entries for t in toks}
        self._compact = "".join(t for _, toks in self._entries for t in toks)[-4000:]

    def _prune(self, now: float) -> None:
        changed = False
        while self._entries and now - self._entries[0][0] > self.max_age:
            self._entries.popleft()
            changed = True
        if changed:
            self._rebuild()

    def _known(self, tok: str) -> bool:
        if tok in self._vocab:
            return True
        if len(tok) < 4:
            return False
        return bool(difflib.get_close_matches(tok, self._vocab, n=1, cutoff=0.8))

    def _novelty(self, tokens: list[str]) -> tuple[int, int]:
        """(content words considered, words not found in assistant speech)."""
        has_digits = any(t.isdigit() for t in self._vocab)
        content = [t for t in tokens if t not in STOPWORDS] or tokens
        considered = novel = 0
        for tok in content:
            if tok in FILLERS:
                continue
            if tok in NEUTRAL_WORDS and (has_digits or tok in self._vocab):
                continue
            considered += 1
            if not self._known(tok):
                novel += 1
        return considered, novel

    def novel_count(self, text: str, *, now: float | None = None) -> int:
        """Number of content words in ``text`` the assistant did not say."""
        self._prune(time.monotonic() if now is None else now)
        tokens = tokenize(text)
        if not tokens:
            return 0
        if not self._entries:
            return len([t for t in tokens if t not in STOPWORDS and t not in FILLERS])
        return self._novelty(tokens)[1]

    def is_backchannel(self, text: str) -> bool:
        tokens = tokenize(text)
        return not tokens or all(t in FILLERS for t in tokens)

    def is_echo(self, text: str, *, now: float | None = None) -> bool:
        """True if ``text`` is (almost) entirely the assistant's own words,
        or contains nothing actionable (empty / filler only)."""
        now = time.monotonic() if now is None else now
        self._prune(now)
        tokens = tokenize(text)
        if not tokens or all(t in FILLERS for t in tokens):
            return True
        if not self._entries:
            return False

        considered, novel = self._novelty(tokens)
        if considered == 0 or novel / considered <= self.novel_ratio:
            return True

        # Tokenisation can differ ("port folio" vs "portfolio"): compare letters.
        compact = "".join(t for t in tokens if t not in NEUTRAL_WORDS)
        if len(compact) >= 8:
            if compact in self._compact:
                return True
            m = difflib.SequenceMatcher(None, compact, self._compact, autojunk=False
                                        ).find_longest_match(0, len(compact), 0, len(self._compact))
            if m.size >= 0.8 * len(compact):
                return True
        return False
