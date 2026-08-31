"""Hybrid retrieval over the three knowledge sources.

PRD FR-2.2 requires hybrid retrieval because Tier-1 queries mix symptom language
("my internet died") with exact tokens ("APN", "eSIM", "*123#", "VoLTE"). Two
lexical views are fused:

* BM25 over word tokens — precise on the exact tokens.
* Character 4-gram cosine — tolerant of typos, plurals, and spacing ("e-SIM",
  "esim", "eSIM"), which pure word matching misses.

Results are fused with Reciprocal Rank Fusion, then re-ranked by source trust
(FR-2.7) and capped per source (FR-2.4) so one source cannot crowd out the rest.
The semantic bridge from symptom language to domain vocabulary is handled ahead
of this module by the LLM query rewrite in ``llm.expand_query``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .ingest import Chunk

_TOKEN_RE = re.compile(r"[a-z0-9#*]+")

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "and",
    "or", "in", "on", "at", "for", "with", "my", "i", "me", "it", "its", "this",
    "that", "do", "does", "did", "how", "what", "why", "when", "can", "you",
    "your", "we", "our", "if", "not", "no", "but", "so", "from", "get", "got",
}


def tokenise(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS]


def char_ngrams(text: str, n: int = 4) -> Counter[str]:
    cleaned = re.sub(r"\s+", " ", text.lower()).strip()
    if len(cleaned) < n:
        return Counter([cleaned] if cleaned else [])
    return Counter(cleaned[i : i + n] for i in range(len(cleaned) - n + 1))


@dataclass
class Hit:
    chunk: Chunk
    score: float  # fused rank score, used for ordering
    bm25: float = 0.0  # raw lexical strength, used for the confidence gate
    ngram: float = 0.0
    bm25_rank: int | None = None
    ngram_rank: int | None = None

    @property
    def relevance(self) -> float:
        """Absolute 0..1 relevance, independent of how the other chunks scored.

        Rank-fusion scores say which chunk is best; they say nothing about whether
        the best chunk is any good. The confidence gate needs the second question
        answered, so it uses raw lexical strength instead.
        """
        saturating_bm25 = self.bm25 / (self.bm25 + 6.0)
        return round(min(1.0, 0.65 * saturating_bm25 + 0.35 * self.ngram), 4)


class HybridRetriever:
    """Small-corpus hybrid retriever. Pure Python — no external index service."""

    K1 = 1.5
    B = 0.75
    RRF_K = 60

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self._doc_tokens = [tokenise(chunk.retrieval_text) for chunk in chunks]
        self._doc_len = [len(tokens) or 1 for tokens in self._doc_tokens]
        self._avg_len = sum(self._doc_len) / len(self._doc_len) if self._doc_len else 1.0
        self._term_freq = [Counter(tokens) for tokens in self._doc_tokens]

        document_freq: Counter[str] = Counter()
        for tokens in self._doc_tokens:
            document_freq.update(set(tokens))
        total = len(chunks) or 1
        self._idf = {
            term: math.log(1 + (total - freq + 0.5) / (freq + 0.5))
            for term, freq in document_freq.items()
        }

        self._doc_ngrams = [char_ngrams(chunk.retrieval_text) for chunk in chunks]
        ngram_df: Counter[str] = Counter()
        for grams in self._doc_ngrams:
            ngram_df.update(grams.keys())
        self._ngram_idf = {
            gram: math.log(1 + total / (freq + 0.5)) for gram, freq in ngram_df.items()
        }
        self._doc_ngram_norm = [
            math.sqrt(sum((count * self._ngram_idf.get(gram, 0.0)) ** 2 for gram, count in grams.items())) or 1.0
            for grams in self._doc_ngrams
        ]

    # --- individual scorers --------------------------------------------------

    def _bm25(self, query: str) -> list[float]:
        query_terms = tokenise(query)
        scores = [0.0] * len(self.chunks)
        for index, freqs in enumerate(self._term_freq):
            length = self._doc_len[index]
            total = 0.0
            for term in query_terms:
                frequency = freqs.get(term, 0)
                if not frequency:
                    continue
                idf = self._idf.get(term, 0.0)
                numerator = frequency * (self.K1 + 1)
                denominator = frequency + self.K1 * (1 - self.B + self.B * length / self._avg_len)
                total += idf * numerator / denominator
            scores[index] = total
        return scores

    def _ngram_cosine(self, query: str) -> list[float]:
        query_grams = char_ngrams(query)
        query_norm = math.sqrt(
            sum((count * self._ngram_idf.get(gram, 0.0)) ** 2 for gram, count in query_grams.items())
        )
        if query_norm == 0:
            return [0.0] * len(self.chunks)
        scores = []
        for index, grams in enumerate(self._doc_ngrams):
            dot = 0.0
            smaller, larger = (query_grams, grams) if len(query_grams) < len(grams) else (grams, query_grams)
            for gram, count in smaller.items():
                other = larger.get(gram)
                if other:
                    weight = self._ngram_idf.get(gram, 0.0) ** 2
                    dot += count * other * weight
            scores.append(dot / (query_norm * self._doc_ngram_norm[index]))
        return scores

    # --- fusion --------------------------------------------------------------

    @staticmethod
    def _ranks(scores: list[float]) -> dict[int, int]:
        ordered = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return {doc: rank for rank, doc in enumerate(ordered, start=1) if scores[doc] > 0}

    def search(self, query: str, top_k: int = 6, max_per_source: int = 3) -> list[Hit]:
        if not self.chunks or not query.strip():
            return []

        bm25_scores = self._bm25(query)
        ngram_scores = self._ngram_cosine(query)
        bm25_ranks = self._ranks(bm25_scores)
        ngram_ranks = self._ranks(ngram_scores)

        fused: list[Hit] = []
        for index, chunk in enumerate(self.chunks):
            bm25_rank = bm25_ranks.get(index)
            ngram_rank = ngram_ranks.get(index)
            if bm25_rank is None and ngram_rank is None:
                continue
            score = 0.0
            if bm25_rank is not None:
                score += 1.0 / (self.RRF_K + bm25_rank)
            if ngram_rank is not None:
                score += 1.0 / (self.RRF_K + ngram_rank)
            # Trust tilt (FR-2.7): a nudge, not an override — it only separates
            # chunks that fusion already ranked close together.
            score *= 1.0 + 0.05 * chunk.trust
            fused.append(
                Hit(
                    chunk=chunk,
                    score=score,
                    bm25=bm25_scores[index],
                    ngram=ngram_scores[index],
                    bm25_rank=bm25_rank,
                    ngram_rank=ngram_rank,
                )
            )

        fused.sort(key=lambda hit: hit.score, reverse=True)

        selected: list[Hit] = []
        per_source: Counter[str] = Counter()
        for hit in fused:
            if per_source[hit.chunk.source] >= max_per_source:
                continue
            selected.append(hit)
            per_source[hit.chunk.source] += 1
            if len(selected) >= top_k:
                break
        return selected


def normalised_top_score(hits: list[Hit]) -> float:
    """Best absolute relevance across the returned hits, for the gate (FR-3.1)."""
    if not hits:
        return 0.0
    return max(hit.relevance for hit in hits)
