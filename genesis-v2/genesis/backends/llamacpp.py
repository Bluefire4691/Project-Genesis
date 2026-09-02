"""
llama.cpp (`llama-server`) backends — the portable default.

One binary, one model format (GGUF), and the widest backend coverage in the
industry: CUDA, ROCm/HIP, Vulkan, SYCL, Metal, OpenCL, CANN (Huawei Ascend),
MUSA (Moore Threads), OpenVINO, Snapdragon, IBM Z. The same .gguf file runs
on all of them, which is exactly the portability property this project wants.

Deliberately NOT Ollama — not for lock-in reasons (it speaks the same
OpenAI-compatible API and stays a drop-in fallback) but for measured
performance: its llama.cpp vendoring lags months, benchmarking ~34 t/s
against 52-56 t/s upstream on AMD hardware.

NOTE: `--embeddings` and `--reranking` are mutually exclusive per process,
so embeddings and reranking each need their own server on their own port.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterator, Sequence

import numpy as np

from .base import (
    BackendUnavailable, Capabilities, ContextOverflow, EmbedKind,
    EmbeddingBackend, LLMBackend, Message, OutOfMemory, RerankBackend,
    SamplingParams,
)

_DEFAULT_LLM_URL    = os.environ.get("GENESIS_LLM_URL",    "http://127.0.0.1:8080")
_DEFAULT_EMBED_URL  = os.environ.get("GENESIS_EMBED_URL",  "http://127.0.0.1:8081")
_DEFAULT_RERANK_URL = os.environ.get("GENESIS_RERANK_URL", "http://127.0.0.1:8082")

_TIMEOUT = float(os.environ.get("GENESIS_HTTP_TIMEOUT", "300"))


def _post(url: str, payload: dict, timeout: float = _TIMEOUT) -> dict:
    """POST JSON, translating every transport/server failure into a
    BackendError subclass. Nothing vendor-specific escapes."""
    try:
        import requests
    except ImportError as exc:                       # pragma: no cover
        raise BackendUnavailable("requests is not installed") from exc

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except Exception as exc:
        raise BackendUnavailable(f"cannot reach {url}: {exc}") from exc

    if resp.status_code >= 400:
        body = (resp.text or "")[:500].lower()
        if "context" in body and ("exceed" in body or "too long" in body):
            raise ContextOverflow(requested=-1, limit=-1)
        if "out of memory" in body or "oom" in body or "alloc" in body:
            raise OutOfMemory(body)
        raise BackendUnavailable(f"{url} returned {resp.status_code}: {body}")

    try:
        return resp.json()
    except Exception as exc:
        raise BackendUnavailable(f"{url} returned non-JSON: {exc}") from exc


def _get(url: str, timeout: float = 10.0) -> dict:
    try:
        import requests
    except ImportError as exc:                       # pragma: no cover
        raise BackendUnavailable("requests is not installed") from exc
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise BackendUnavailable(f"cannot reach {url}: {exc}") from exc


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

class LlamaCppLLM(LLMBackend):
    """Chat completions against llama-server's OpenAI-compatible endpoint."""

    def __init__(self, base_url: str = _DEFAULT_LLM_URL,
                 model_alias: str = "local", timeout: float = _TIMEOUT):
        self._base = base_url.rstrip("/")
        self._model = model_alias
        self._timeout = timeout
        self._caps: Capabilities | None = None

    # -- helpers ----------------------------------------------------------

    def _payload(self, messages: Sequence[Message],
                 params: SamplingParams, stream: bool) -> dict:
        p: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "stream": stream,
        }
        if params.stop:
            p["stop"] = list(params.stop)
        if params.seed is not None:
            p["seed"] = params.seed
        if params.json_schema is not None:
            # llama-server supports constrained decoding via response_format.
            p["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True,
                                "schema": params.json_schema},
            }
        return p

    # -- interface --------------------------------------------------------

    def generate(self, messages: Sequence[Message],
                 params: SamplingParams | None = None) -> str:
        params = params or SamplingParams()
        data = _post(f"{self._base}/v1/chat/completions",
                     self._payload(messages, params, stream=False),
                     timeout=self._timeout)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendUnavailable(
                f"unexpected completion shape: {str(data)[:200]}") from exc

    def generate_stream(self, messages: Sequence[Message],
                        params: SamplingParams | None = None) -> Iterator[str]:
        params = params or SamplingParams()
        try:
            import requests
        except ImportError as exc:                   # pragma: no cover
            raise BackendUnavailable("requests is not installed") from exc
        try:
            resp = requests.post(
                f"{self._base}/v1/chat/completions",
                json=self._payload(messages, params, stream=True),
                timeout=self._timeout, stream=True)
            resp.raise_for_status()
        except Exception as exc:
            raise BackendUnavailable(f"stream failed: {exc}") from exc

        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8", "replace")
            if not line.startswith("data: "):
                continue
            body = line[6:]
            if body.strip() == "[DONE]":
                return
            try:
                delta = json.loads(body)["choices"][0].get("delta", {})
            except Exception:
                continue
            piece = delta.get("content")
            if piece:
                yield piece

    def tokenize(self, text: str) -> list[int]:
        data = _post(f"{self._base}/tokenize", {"content": text},
                     timeout=min(30.0, self._timeout))
        toks = data.get("tokens")
        if not isinstance(toks, list):
            raise BackendUnavailable(f"unexpected tokenize shape: {str(data)[:200]}")
        return toks

    def capabilities(self) -> Capabilities:
        if self._caps is not None:
            return self._caps
        try:
            props = _get(f"{self._base}/props")
        except BackendUnavailable:
            raise
        ctx = (props.get("default_generation_settings", {}).get("n_ctx")
               or props.get("n_ctx") or 4096)
        self._caps = Capabilities(
            context_length=int(ctx),
            supports_json_schema=True,
            supports_streaming=True,
            supports_logprobs=True,
            max_batch=1,
            detail={"server": "llama.cpp",
                    "model_path": props.get("model_path", "")},
        )
        return self._caps


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

# Qwen3-Embedding is asymmetric: queries get an instruction prefix, documents
# do not. Getting this backwards silently degrades retrieval.
_QUERY_PREFIX = ("Instruct: Given a search query, retrieve relevant passages\n"
                 "Query: ")


class LlamaCppEmbedding(EmbeddingBackend):
    """Embeddings from a llama-server started with --embeddings."""

    def __init__(self, base_url: str = _DEFAULT_EMBED_URL,
                 model_id: str = "qwen3-embedding-0.6b",
                 dim: int | None = None,
                 query_prefix: str = _QUERY_PREFIX,
                 timeout: float = _TIMEOUT):
        self._base = base_url.rstrip("/")
        self._model_id = model_id
        self._dim = dim
        self._query_prefix = query_prefix
        self._timeout = timeout

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = int(self.embed(["dimension probe"]).shape[1])
        return self._dim

    @property
    def model_id(self) -> str:
        return self._model_id

    def embed(self, texts: Sequence[str], kind: EmbedKind = "doc") -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, self._dim or 0), dtype=np.float32)

        payload_texts = ([self._query_prefix + t for t in texts]
                         if kind == "query" else texts)
        data = _post(f"{self._base}/v1/embeddings",
                     {"model": self._model_id, "input": payload_texts},
                     timeout=self._timeout)
        try:
            rows = sorted(data["data"], key=lambda d: d.get("index", 0))
            vecs = np.asarray([r["embedding"] for r in rows], dtype=np.float32)
        except (KeyError, TypeError, ValueError) as exc:
            raise BackendUnavailable(
                f"unexpected embeddings shape: {str(data)[:200]}") from exc

        if vecs.ndim != 2 or vecs.shape[0] != len(texts):
            raise BackendUnavailable(
                f"expected {len(texts)} vectors, got shape {vecs.shape}")

        # L2-normalize here so every consumer can assume cosine == dot.
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        np.maximum(norms, 1e-12, out=norms)
        return (vecs / norms).astype(np.float32)


# ---------------------------------------------------------------------------
# Reranking
# ---------------------------------------------------------------------------

class LlamaCppReranker(RerankBackend):
    """Reranking from a llama-server started with --reranking --pooling rank.

    Includes a startup validation for a known GGUF conversion bug: some
    Qwen3-Reranker conversions ship without `cls.output.weight` and silently
    emit ~1e-23 scores for everything. Silent uniform garbage is worse than
    a crash, so `validate()` asserts a known-relevant pair outscores a
    known-irrelevant one.
    """

    _DEGENERATE = 1e-12

    def __init__(self, base_url: str = _DEFAULT_RERANK_URL,
                 model_id: str = "qwen3-reranker-0.6b",
                 timeout: float = _TIMEOUT):
        self._base = base_url.rstrip("/")
        self._model_id = model_id
        self._timeout = timeout

    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        docs = list(docs)
        if not docs:
            return []
        data = _post(f"{self._base}/v1/rerank",
                     {"model": self._model_id, "query": query,
                      "documents": docs, "top_n": len(docs)},
                     timeout=self._timeout)
        try:
            results = data.get("results", data.get("data", []))
            scores = [0.0] * len(docs)
            for r in results:
                scores[int(r["index"])] = float(r["relevance_score"])
            return scores
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise BackendUnavailable(
                f"unexpected rerank shape: {str(data)[:200]}") from exc

    def validate(self) -> None:
        """Raise BackendUnavailable if the model emits degenerate scores.
        Call once at startup — a bad GGUF conversion fails silently otherwise."""
        scores = self.rerank(
            "What is the capital of France?",
            ["Paris is the capital and largest city of France.",
             "The mitochondrion is an organelle found in eukaryotic cells."],
        )
        if max(abs(s) for s in scores) < self._DEGENERATE:
            raise BackendUnavailable(
                "reranker returned degenerate (~0) scores for all documents — "
                "the GGUF is likely missing cls.output.weight; re-convert it")
        if scores[0] <= scores[1]:
            raise BackendUnavailable(
                f"reranker failed a sanity pair (relevant={scores[0]:.4g} "
                f"<= irrelevant={scores[1]:.4g}); check model and --pooling rank")
