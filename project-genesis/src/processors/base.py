"""
Base class for all sensory processors.

Every processor must:
1. Accept input and produce a ProcessorOutput
2. NEVER raise an exception — always return something
3. Be independently replaceable without affecting other processors
"""

from abc import ABC, abstractmethod
from typing import Any
import traceback

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import ProcessorOutput


class BaseProcessor(ABC):
    """
    Abstract base for sensory processors.

    Subclasses implement _process() with their specific logic.
    The public process() method wraps it in never-crash error handling.
    """

    name: str = "base"

    def process(self, data: Any) -> ProcessorOutput:
        """
        Public entry point. Wraps _process in error handling so
        processors never crash — they always return something.
        """
        try:
            return self._process(data)
        except Exception as e:
            # Error is data, not a stop condition
            return ProcessorOutput(
                source=self.name,
                input_data=data,
                extracted={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                },
                importance=0.1,  # Low importance — we couldn't process it well
                suggested_key=f"error:{self.name}:{hash(str(data)) % 10000}",
                context=f"Processor '{self.name}' encountered an error: {type(e).__name__}: {e}",
                confidence=0.0,  # Zero confidence — this is a fallback
            )

    @abstractmethod
    def _process(self, data: Any) -> ProcessorOutput:
        """Subclasses implement their specific processing logic here."""
        ...
