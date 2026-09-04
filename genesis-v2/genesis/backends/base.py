"""
Backend interfaces — the portability boundary.

Design principle: the engine runs on anything. CUDA is an optimization, never
an assumption. Export controls have already moved much of the industry onto
alternative silicon; an architecture that assumes NVIDIA inherits that
fragility.

WHAT MUST NEVER CROSS THIS BOUNDARY
-----------------------------------
  * Tensors, device objects, dtypes, streams, memory handles.
    Nothing but plain Python and numpy.ndarray.
  * Vendor strings (cuda / rocm / vulkan / nvidia / amd / metal / sycl).
    Enforced by tools/lint_vendor_strings.py in CI.
  * Model file formats and paths. Callers ask for an ALIAS ("llm.main")
    and get a handle. GGUF vs safetensors vs ONNX is a backend detail.
  * Quantization vocabulary (Q4_K_M, NF4, INT8) — backend config only.
  * Sampling-parameter dialects — normalized here, translated inside.
  * Tokenizer identity — callers count tokens via LLMBackend.tokenize().
  * Backend-specific exceptions — caught at the boundary and re-raised as
    the error types below, so an OOM is actionable without knowing who
    threw it.

Model identity is a config alias, not a filename. Swapping silicon and
swapping model are then the same one-line change — which is the actual test
of whether this abstraction holds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator, Literal, Sequence

import numpy as np

EmbedKind = Literal["query", "doc"]


# ---------------------------------------------------------------------------
# Errors — the only exception types allowed to escape a backend
# ---------------------------------------------------------------------------

class BackendError(Exception):
    """Base for every error crossing the backend boundary."""


class BackendUnavailable(BackendError):
    """Backend cannot serve requests (not built, not running, unreachable)."""


class OutOfMemory(BackendError):
    """Device or host ran out of memory. Caller may retry smaller."""


class ContextOverflow(BackendError):
    """Request exceeded the model's context window."""

    def __init__(self, requested: int, limit: int):
        super().__init__(f"requested {requested} tokens, limit {limit}")
        self.requested = requested
        self.limit = limit


class ModelNotFound(BackendError):
    """No model is registered under the requested alias."""


# ---------------------------------------------------------------------------
# Normalized parameters — one dialect, translated inside each backend
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SamplingParams:
    """Normalized sampling parameters. Backends translate to their own names."""
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.95
    seed: int | None = None
    stop: tuple[str, ...] = ()
    json_schema: dict | None = None   # constrained decoding when supported

    def __post_init__(self):
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be in [0, 2]")
        if not 0.0 < self.top_p <= 1.0:
            raise ValueError("top_p must be in (0, 1]")


@dataclass(frozen=True)
class Capabilities:
    """What a backend can actually do. Callers branch on this, not on vendor."""
    context_length: int
    supports_json_schema: bool = False
    supports_streaming: bool = False
    supports_logprobs: bool = False
    max_batch: int = 1
    # Free-form, informational only — MUST NOT be branched on by callers.
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


# ---------------------------------------------------------------------------
# The four interfaces. There are exactly four, deliberately.
# ---------------------------------------------------------------------------

class LLMBackend(ABC):
    """Text generation. Implementations: llama-server, (fallback) Ollama, fake."""

    @abstractmethod
    def generate(self, messages: Sequence[Message],
                 params: SamplingParams | None = None) -> str:
        """Return the completion text. Raises only BackendError subclasses."""

    def generate_stream(self, messages: Sequence[Message],
                        params: SamplingParams | None = None) -> Iterator[str]:
        """Yield completion chunks. Default: non-streaming single yield."""
        yield self.generate(messages, params)

    @abstractmethod
    def tokenize(self, text: str) -> list[int]:
        """Token ids — for budgeting. Callers must never import a tokenizer."""

    def count_tokens(self, text: str) -> int:
        return len(self.tokenize(text))

    @abstractmethod
    def capabilities(self) -> Capabilities:
        ...

    def health(self) -> bool:
        """Cheap liveness check. False rather than raising."""
        try:
            self.capabilities()
            return True
        except BackendError:
            return False


class EmbeddingBackend(ABC):
    """Dense embeddings. The embedder is FROZEN FOREVER once chosen:
    re-embedding invalidates the memory store and rewrites the agent's past."""

    @abstractmethod
    def embed(self, texts: Sequence[str], kind: EmbedKind = "doc") -> np.ndarray:
        """Return float32 array, shape (len(texts), dim), L2-normalized.

        `kind` matters for asymmetric models (Qwen3-Embedding wants an
        instruction prefix on queries but not documents)."""

    @property
    @abstractmethod
    def dim(self) -> int:
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Stable identifier stored alongside every vector, so a future
        migration can tell which model produced which row."""


class RerankBackend(ABC):
    """Cross-encoder reranking."""

    @abstractmethod
    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        """Relevance scores aligned with `docs`. Higher is better."""


class TrainerBackend(ABC):
    """Small continuously-trained models (world model, RND, ranker).

    These run on CPU by default and that is the FAST choice, not a
    compromise: a 5M-param MLP is kernel-launch-bound on a GPU below
    batch ~1024, and CPU leaves the accelerator free for the LLM."""

    @abstractmethod
    def fit_step(self, batch: dict[str, np.ndarray]) -> float:
        """One optimization step. Returns loss."""

    @abstractmethod
    def predict(self, x: np.ndarray) -> np.ndarray:
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        ...

    @abstractmethod
    def load(self, path: str) -> None:
        ...


# ---------------------------------------------------------------------------
# Registry — alias -> backend. Callers name capabilities, never models.
# ---------------------------------------------------------------------------

class BackendRegistry:
    """Maps stable aliases ('llm.main', 'embed.default') to live backends.

    Aliases are the caller's entire vocabulary. Swapping silicon or swapping
    model is a config change here, never a code change anywhere else.
    """

    def __init__(self) -> None:
        self._backends: dict[str, Any] = {}

    def register(self, alias: str, backend: Any) -> None:
        if not alias or "." not in alias:
            raise ValueError(
                f"alias must look like 'kind.name', got {alias!r}")
        self._backends[alias] = backend

    def get(self, alias: str) -> Any:
        try:
            return self._backends[alias]
        except KeyError:
            raise ModelNotFound(
                f"no backend registered as {alias!r}; "
                f"registered: {sorted(self._backends)}") from None

    def llm(self, alias: str = "llm.main") -> LLMBackend:
        return self.get(alias)

    def embedder(self, alias: str = "embed.default") -> EmbeddingBackend:
        return self.get(alias)

    def reranker(self, alias: str = "rerank.default") -> RerankBackend:
        return self.get(alias)

    def aliases(self) -> list[str]:
        return sorted(self._backends)

    def __contains__(self, alias: str) -> bool:
        return alias in self._backends
