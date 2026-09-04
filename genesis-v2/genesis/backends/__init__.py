"""Backend abstraction — the hardware portability boundary.

Callers import from here and speak only in aliases and capabilities.
Vendor names live below this line and nowhere else.
"""

from .base import (
    BackendError, BackendRegistry, BackendUnavailable, Capabilities,
    ContextOverflow, EmbeddingBackend, LLMBackend, Message, ModelNotFound,
    OutOfMemory, RerankBackend, SamplingParams, TrainerBackend,
)

__all__ = [
    "BackendError", "BackendRegistry", "BackendUnavailable", "Capabilities",
    "ContextOverflow", "EmbeddingBackend", "LLMBackend", "Message",
    "ModelNotFound", "OutOfMemory", "RerankBackend", "SamplingParams",
    "TrainerBackend",
]
