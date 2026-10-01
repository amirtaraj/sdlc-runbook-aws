"""In-memory BM25 keyword index over the synthetic standards in data/knowledge_base/."""
import json
import math
import re
from collections import Counter
from pathlib import Path

_STOPWORDS = set(
    "a an and are as at be by for from has have in is it its of on or that the to was were will with "
    "this these those should must can may not no all any each every into than then there their they".split()
)


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS and len(t) > 1]


class Bm25Index:
    def __init__(self, docs: list[dict], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self._k1, self._b = k1, b
        # Titles count twice: they are short and very descriptive.
        self._terms = [Counter(_tokens(f"{d['title']} {d['title']} {d.get('category', '')} {d['content']}")) for d in docs]
        self._lengths = [sum(t.values()) for t in self._terms]
        self._avg_len = sum(self._lengths) / len(docs) if docs else 0
        df = Counter(term for terms in self._terms for term in terms)
        n = len(docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    @classmethod
    def from_file(cls, path: Path) -> "Bm25Index":
        return cls(json.loads(path.read_text(encoding="utf-8")) if path.is_file() else [])

    def search(self, query: str, top: int) -> list[tuple[dict, float]]:
        q = set(_tokens(query))
        scored = []
        for doc, terms, length in zip(self.docs, self._terms, self._lengths):
            score = 0.0
            for t in q & terms.keys():
                tf = terms[t]
                score += self._idf[t] * tf * (self._k1 + 1) / (tf + self._k1 * (1 - self._b + self._b * length / self._avg_len))
            if score > 0:
                scored.append((doc, round(score, 4)))
        return sorted(scored, key=lambda x: x[1], reverse=True)[:top]
