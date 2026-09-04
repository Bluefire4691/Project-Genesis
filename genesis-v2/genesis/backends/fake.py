"""
Deterministic fake backends — the primary testing substrate.

The evaluation plan calls for three test layers; this module enables the
first and largest of them:

  1. CONTRACT TESTS with a fake LLM — fast, deterministic, cover all
     orchestration logic. Most new tests live here.
  2. Property/invariant tests — assert bounds, not values.
  3. A slow, scored EVAL SUITE against a real model. Reports a number and a
     regression delta; it does NOT gate CI.

These fakes are deterministic functions of their input (seeded by content
hash), so tests can assert exact values without a model, and embeddings have
real geometry — texts sharing tokens land closer together — which means
retrieval logic can be tested meaningfully rather than trivially.
"""

from __future__ import annotations

import hashlib
import re
from typing import Sequence

import numpy as np

from .base import (
    BackendUnavailable, Capabilities, ContextOverflow, EmbedKind,
    EmbeddingBackend, LLMBackend, Message, RerankBackend, SamplingParams,
    TrainerBackend,
)


def _seed_of(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class FakeLLM(LLMBackend):
    """Deterministic generator. Optionally scripted with canned responses."""

    def __init__(self, responses: dict[str, str] | None = None,
                 context_length: int = 4096, fail: Exception | None = None):
        self._responses = responses or {}
        self._context_length = context_length
        self._fail = fail
        self.calls: list[list[Message]] = []          # inspectable by tests

    def generate(self, messages: Sequence[Message],
                 params: SamplingParams | None = None) -> str:
        if self._fail is not None:
            raise self._fail
        msgs = list(messages)
        self.calls.append(msgs)
        prompt = "\n".join(m.content for m in msgs)

        n_prompt = self.count_tokens(prompt)
        if n_prompt > self._context_length:
            raise ContextOverflow(requested=n_prompt, limit=self._context_length)

        for key, canned in self._responses.items():
            if key in prompt:
                return canned

        params = params or SamplingParams()
        rng = np.random.default_rng(_seed_of(prompt) ^ (params.seed or 0))
        vocab = _tokens(prompt) or ["genesis"]
        n = max(1, min(params.max_tokens, 12))
        return " ".join(str(vocab[int(i)]) for i in rng.integers(0, len(vocab), n))

    def tokenize(self, text: str) -> list[int]:
        # Deterministic and roughly word-shaped; good enough for budgeting tests.
        return [_seed_of(t) % 50000 for t in _tokens(text)] or [0]

    def capabilities(self) -> Capabilities:
        if self._fail is not None:
            raise self._fail
        return Capabilities(
            context_length=self._context_length,
            supports_json_schema=True,
            supports_streaming=True,
            max_batch=8,
            detail={"server": "fake"},
        )


class FakeEmbedding(EmbeddingBackend):
    """Hashed bag-of-words embeddings with real geometry.

    Texts sharing vocabulary genuinely land closer together, so retrieval,
    clustering and novelty logic can be tested without a model.
    """

    def __init__(self, dim: int = 64, model_id: str = "fake-embed-v1"):
        self._dim = dim
        self._model_id = model_id

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model_id(self) -> str:
        return self._model_id

    def embed(self, texts: Sequence[str], kind: EmbedKind = "doc") -> np.ndarray:
        texts = list(texts)
        out = np.zeros((len(texts), self._dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for tok in _tokens(text):
                out[i, _seed_of(tok) % self._dim] += 1.0
            if kind == "query":
                # Small asymmetry so query/doc mix-ups are detectable in tests.
                out[i, 0] += 0.5
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        np.maximum(norms, 1e-12, out=norms)
        return (out / norms).astype(np.float32)


class FakeReranker(RerankBackend):
    """Token-overlap scoring — monotone in genuine relevance."""

    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        q = set(_tokens(query))
        scores = []
        for doc in docs:
            d = set(_tokens(doc))
            scores.append(len(q & d) / len(q | d) if (q or d) else 0.0)
        return scores


class FakeTrainer(TrainerBackend):
    """Linear least-squares stand-in; loss genuinely decreases."""

    def __init__(self, in_dim: int, out_dim: int, lr: float = 0.05):
        rng = np.random.default_rng(0)
        self._w = rng.normal(0, 0.01, (in_dim, out_dim)).astype(np.float32)
        self._lr = lr
        self.steps = 0

    def fit_step(self, batch: dict[str, np.ndarray]) -> float:
        x, y = np.asarray(batch["x"], np.float32), np.asarray(batch["y"], np.float32)
        pred = x @ self._w
        err = pred - y
        self._w -= self._lr * (x.T @ err) / max(1, len(x))
        self.steps += 1
        return float((err ** 2).mean())

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(x, np.float32) @ self._w

    def save(self, path: str) -> None:
        np.save(path, self._w)

    def load(self, path: str) -> None:
        self._w = np.load(path if path.endswith(".npy") else path + ".npy")


class UnavailableLLM(LLMBackend):
    """Always fails — for testing degradation paths."""

    def generate(self, messages, params=None) -> str:
        raise BackendUnavailable("fake outage")

    def tokenize(self, text: str) -> list[int]:
        raise BackendUnavailable("fake outage")

    def capabilities(self) -> Capabilities:
        raise BackendUnavailable("fake outage")
