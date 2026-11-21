"""Search over DocumentChunks with BM25 ranking.

Pure Python over the Django database: no extra service to install, works
offline and on Windows. The index is built lazily and rebuilt when chunks
change (checked by count and highest id, so it stays correct across processes).
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass

from django.db.models import Max

from .models import DocumentChunk

STOPWORDS = frozenset(
    """a an and are as at be been but by can could did do does for from had has have how i if in into is it its
    me my of on or our so than that the their them then there these they this those to was we were what when
    where which while who whom why will with would you your about above after again also any because before
    being between both each few more most other over same should some such only own very just tell explain
    please give describe define""".split()
)

_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in _WORD.findall(text.lower()):
        if len(word) < 3 or word in STOPWORDS:
            continue
        for suffix in ("ing", "ies", "es", "s", "ed"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 4:
                word = word[: -len(suffix)] + ("y" if suffix == "ies" else "")
                break
        tokens.append(word)
    return tokens


@dataclass
class Hit:
    chunk: DocumentChunk
    score: float


class BM25Index:
    k1 = 1.5
    b = 0.75

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._signature: tuple | None = None
        self._ids: list[int] = []
        self._tfs: list[Counter] = []
        self._lengths: list[int] = []
        self._df: Counter = Counter()
        self._avg_len = 0.0

    def invalidate(self) -> None:
        with self._lock:
            self._signature = None

    def _current_signature(self) -> tuple:
        agg = DocumentChunk.objects.aggregate(top=Max("id"))
        return (DocumentChunk.objects.count(), agg["top"])

    def _ensure(self) -> None:
        sig = self._current_signature()
        with self._lock:
            if sig == self._signature:
                return
            ids, tfs, lengths, df = [], [], [], Counter()
            for pk, text in DocumentChunk.objects.values_list("id", "text").iterator():
                tokens = tokenize(text)
                tf = Counter(tokens)
                ids.append(pk)
                tfs.append(tf)
                lengths.append(len(tokens))
                df.update(tf.keys())
            self._ids, self._tfs, self._lengths, self._df = ids, tfs, lengths, df
            self._avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0
            self._signature = sig

    def search(self, query: str, k: int = 4, min_score: float = 0.5) -> list[Hit]:
        self._ensure()
        terms = set(tokenize(query))
        n = len(self._ids)
        if not terms or not n:
            return []
        scored = []
        for i, tf in enumerate(self._tfs):
            score = 0.0
            for term in terms:
                f = tf.get(term)
                if not f:
                    continue
                idf = math.log(1 + (n - self._df[term] + 0.5) / (self._df[term] + 0.5))
                norm = f + self.k1 * (1 - self.b + self.b * self._lengths[i] / (self._avg_len or 1))
                score += idf * f * (self.k1 + 1) / norm
            if score >= min_score:
                scored.append((score, self._ids[i]))
        scored.sort(reverse=True)
        top = scored[:k]
        chunks = DocumentChunk.objects.in_bulk([pk for _, pk in top])
        return [Hit(chunks[pk], round(score, 3)) for score, pk in top if pk in chunks]


index = BM25Index()


def search(query: str, k: int = 4) -> list[Hit]:
    return index.search(query, k=k)


def overlap_ratio(answer: str, sources: list[str]) -> float:
    """Share of the answer's content words that appear in the sources (0..1)."""
    answer_terms = set(tokenize(answer))
    if not answer_terms:
        return 0.0
    source_terms = set()
    for text in sources:
        source_terms.update(tokenize(text))
    return len(answer_terms & source_terms) / len(answer_terms)
