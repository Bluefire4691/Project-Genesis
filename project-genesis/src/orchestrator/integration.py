"""
Integration Layer — M4: Cross-Processor Synthesis.

All processors see all input. Significance is determined by how much
each processor's findings connect to what's already in the attention
window. Cross-modal concepts — things multiple processors independently
found in the same input — are explicitly linked in the association graph.

This is where the Orchestrator stops routing and starts synthesizing.

Three things happen here that didn't happen before:

    1. Multi-processor dispatch
       Every available processor sees every input. TextProcessor,
       NumericProcessor, PatternProcessor all return their best read.
       Low-confidence outputs are still outputs — they signal "I
       couldn't find much here," which is information too.

    2. Context scoring
       Each processor output is scored against the current attention
       window. Strong overlap with what's already in working memory
       = high context score. Something that connects to nothing active
       = low context score. This is how the same input can be highly
       significant in one moment and unremarkable in another.

    3. Cross-modal concept detection
       Concepts that appear in multiple processor outputs for the
       same input are explicitly linked. TextProcessor and
       NumericProcessor both finding "temperature" in the same input
       means temperature is important from two independent angles.
       That double-grounding creates a strong explicit association.

The combined significance formula:
    significance = processor_confidence * 0.5 + context_score * 0.5

Both matter equally. High-confidence output with no context connection
is unremarkable. Low-confidence output that connects to active context
may still be meaningful.
"""

import re
import sys
import os
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.types import ProcessorOutput
from memory.memory import MemorySystem


# Stop-words for concept extraction — these don't carry meaning
_STOP = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "that", "this", "it", "its", "not", "no", "as", "up", "out", "any",
    "can", "do", "did", "has", "had", "have", "will", "would", "could",
    "should", "may", "might", "what", "which", "who", "how", "when",
    "where", "why", "there", "their", "they", "we", "you", "i", "he",
    "she", "about", "into", "than", "then", "also", "just", "some",
    "all", "more", "most", "other", "such", "each", "both", "between",
}


@dataclass
class SynthesisResult:
    """
    The integrated output from running all processors on a single input.

    primary_output:       Output from the processor matching input_type hint.
                          Used for curriculum eval and the main memory key.
    secondary_outputs:    Outputs from all other processors that ran.
    significance:         Combined context-weighted significance (0.0–1.0).
    context_score:        How much this input connected to current attention.
    cross_modal_concepts: Concepts independently found by 2+ processors.
    processors_run:       Which processors contributed (name list).
    context_terms:        All attention terms extracted — used for update_attention.
    processor_votes:      M16 — how many independent processors found each concept.
                          Used to boost relation confidence when multiple processors
                          independently confirm the same concept (Hawkins voting).
    """
    primary_output: ProcessorOutput
    secondary_outputs: list[ProcessorOutput] = field(default_factory=list)
    significance: float = 0.5
    context_score: float = 0.0
    cross_modal_concepts: list[str] = field(default_factory=list)
    processors_run: list[str] = field(default_factory=list)
    context_terms: list[str] = field(default_factory=list)
    processor_votes: dict = field(default_factory=dict)


class IntegrationLayer:
    """
    Runs all available processors on every input, scores their outputs
    against current context, and identifies cross-modal connections.

    The MemorySystem is read (for current attention context) but never
    written to here — storage is the Orchestrator's responsibility.
    """

    def __init__(self, memory: MemorySystem):
        self._memory = memory

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def synthesize(
        self,
        outputs: list[ProcessorOutput],
        primary_source: str,
    ) -> SynthesisResult:
        """
        Synthesize outputs from multiple processors into a unified result.

        Args:
            outputs:        All processor outputs for this input (may include
                            error/low-confidence outputs).
            primary_source: The processor name that matches the input_type hint.
                            Its output becomes the primary for curriculum eval.

        Returns:
            SynthesisResult with significance scoring and cross-modal concepts.
        """
        if not outputs:
            # Shouldn't happen, but handle gracefully
            return SynthesisResult(
                primary_output=_empty_output(primary_source),
                processors_run=[],
            )

        # Separate primary from secondary
        primary = next(
            (o for o in outputs if o.source == primary_source),
            outputs[0],
        )
        secondary = [o for o in outputs if o.source != primary_source]

        # Get current attention context (what's in working memory right now)
        attention_terms = self._current_attention_terms()

        # Score each output against current context
        scored: list[tuple[ProcessorOutput, float, float]] = []  # (output, ctx_score, significance)
        for output in outputs:
            ctx_score = self._score_context(output, attention_terms)
            sig = self._combined_significance(output.confidence, ctx_score)
            scored.append((output, ctx_score, sig))

        # Primary's combined significance drives the overall result
        primary_ctx = next(
            (ctx for o, ctx, _ in scored if o.source == primary_source),
            0.0,
        )
        primary_sig = next(
            (sig for o, _, sig in scored if o.source == primary_source),
            primary.confidence,
        )

        # Find cross-modal concepts and build processor vote counts (M16)
        useful_outputs = [o for o in outputs if o.confidence > 0.05]
        cross_modal = self._find_cross_modal_concepts(useful_outputs)

        # M16: count independent processor votes per concept (Hawkins voting).
        # A concept confirmed by 2+ processors is more robustly grounded than
        # one seen by a single processor, even many times.
        processor_votes: dict[str, int] = {}
        for output in useful_outputs:
            for concept in self._extract_concepts(output):
                processor_votes[concept] = processor_votes.get(concept, 0) + 1

        # Build unified attention terms from all outputs
        all_terms: set[str] = set(attention_terms)
        for output in useful_outputs:
            all_terms.update(self._extract_concepts(output))

        return SynthesisResult(
            primary_output=primary,
            secondary_outputs=secondary,
            significance=round(primary_sig, 4),
            context_score=round(primary_ctx, 4),
            cross_modal_concepts=cross_modal,
            processors_run=[o.source for o in outputs],
            context_terms=sorted(all_terms)[:20],  # cap for storage efficiency
            processor_votes=processor_votes,
        )

    # ------------------------------------------------------------------
    # Context scoring
    # ------------------------------------------------------------------

    def _current_attention_terms(self) -> set[str]:
        """
        Extract concept terms from the current working memory attention window.
        These define "what Genesis is thinking about right now."
        """
        terms: set[str] = set()
        window = self._memory._working.attention_window(top_k=10)
        for _, mem in window:
            terms.update(re.findall(r"\b\w{3,}\b", mem.content.lower()))
            terms.update(re.findall(r"\b\w{3,}\b", mem.context.lower()))
        terms -= _STOP
        return terms

    def _score_context(
        self, output: ProcessorOutput, attention_terms: set[str]
    ) -> float:
        """
        Score how much this output connects to the current attention window.

        0.0 = no connection to anything currently active.
        1.0 = strong overlap with current attention context.
        """
        if not attention_terms or output.confidence < 0.05:
            return 0.0

        output_concepts = self._extract_concepts(output)
        if not output_concepts:
            return 0.0

        overlap = len(attention_terms & output_concepts)
        # Normalize by output concepts (how much of what this processor found
        # is already contextually active)
        return min(1.0, overlap / max(1, len(output_concepts)))

    # ------------------------------------------------------------------
    # Cross-modal concept detection
    # ------------------------------------------------------------------

    def _find_cross_modal_concepts(
        self, outputs: list[ProcessorOutput]
    ) -> list[str]:
        """
        Find concepts that appear in 2 or more processor outputs.

        These are the most robustly grounded concepts in the input —
        multiple independent processors independently found them.
        """
        if len(outputs) < 2:
            return []

        concept_counts: dict[str, int] = {}
        for output in outputs:
            for concept in self._extract_concepts(output):
                concept_counts[concept] = concept_counts.get(concept, 0) + 1

        return sorted(
            [c for c, count in concept_counts.items() if count >= 2],
            key=lambda c: concept_counts[c],
            reverse=True,
        )[:10]  # cap at 10 most shared concepts

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_concepts(self, output: ProcessorOutput) -> set[str]:
        """
        Extract meaningful concept strings from a ProcessorOutput.
        Draws from extracted fields and the context string.
        """
        concepts: set[str] = set()

        # Structured fields
        for kw in output.extracted.get("keywords", []):
            concepts.add(str(kw).lower())
        for cat in output.extracted.get("categories", []):
            concepts.add(str(cat).lower())
        if output.extracted.get("label"):
            concepts.add(str(output.extracted["label"]).lower())
        if output.extracted.get("trend"):
            concepts.add(str(output.extracted["trend"]).lower())

        # Context string words
        words = re.findall(r"\b\w{3,}\b", output.context.lower())
        concepts.update(w for w in words if w not in _STOP)

        # Source type itself is a concept
        concepts.add(output.source)

        return concepts - _STOP

    @staticmethod
    def _combined_significance(confidence: float, context_score: float) -> float:
        """
        Combine processor confidence and context score into a single significance.

        Equal weight: both confidence and context connection matter.
        A highly confident output with no context connection is unremarkable.
        A low-confidence output that connects to active context may still matter.
        """
        return confidence * 0.5 + context_score * 0.5


def _empty_output(source: str) -> ProcessorOutput:
    """Fallback for edge case where no outputs were produced."""
    return ProcessorOutput(
        source=source,
        input_data=None,
        extracted={},
        importance=0.0,
        suggested_key=f"empty:{source}",
        context=f"No output from {source}",
        confidence=0.0,
    )
