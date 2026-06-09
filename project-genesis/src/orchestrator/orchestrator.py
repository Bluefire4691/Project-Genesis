"""
The Orchestrator — Central Hypervisor.

Routes input to processors, evaluates outputs, manages memory decisions,
and controls learning progression. It doesn't process data itself — it
decides what gets processed, by whom, and what to do with the results.

Like the brain's executive function: coordination, not computation.
"""

import json
from typing import Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import ProcessorOutput
from processors import TextProcessor, NumericProcessor, PatternProcessor
from memory.memory import MemorySystem
from curriculum.curriculum import CurriculumEngine


class Orchestrator:
    """
    The central coordinating intelligence.

    Never crashes. Every decision is logged. Every error is data.
    """

    def __init__(self, verbose: bool = True):
        self.processors = {
            "text": TextProcessor(),
            "numeric": NumericProcessor(),
            "pattern": PatternProcessor(),
        }
        self.memory = MemorySystem()
        self.curriculum = CurriculumEngine()
        self.verbose = verbose
        self.cycle_count = 0
        self.log: list[str] = []

    def _log(self, msg: str):
        self.log.append(msg)
        if self.verbose:
            print(f"  [{self.curriculum.current_stage.name}] {msg}")

    def process_input(self, input_type: str, data: Any) -> dict:
        """
        Main entry point. Routes input, evaluates results, manages memory.
        Never raises an exception — always returns a result dict.
        """
        self.cycle_count += 1

        try:
            return self._do_process(input_type, data)
        except Exception as e:
            # Ultimate fallback — even the orchestrator's own logic is wrapped
            self._log(f"⚠ Orchestrator error (non-fatal): {e}")
            return {
                "status": "degraded",
                "reason": str(e),
                "cycle": self.cycle_count,
            }

    def _do_process(self, input_type: str, data: Any) -> dict:
        """Internal processing — the actual work."""
        processor = self.processors.get(input_type)
        if not processor:
            self._log(f"⚠ No processor for '{input_type}' — routing to text as fallback")
            processor = self.processors["text"]
            data = str(data)

        # Process
        output = processor.process(data)
        self._log(f"→ {output.source} processor: {output.context}")

        # Evaluate against curriculum
        eval_score = self.curriculum.evaluate_processing(output)
        self.curriculum.record_score(eval_score)
        self._log(f"  Eval: {eval_score:.2f} | Stage avg: {self.curriculum.stage_scores[self.curriculum.current_stage]:.2f}")

        # Store in memory (always — total retention)
        raw = str(data) if not isinstance(data, str) else data
        memory_content = f"{raw} | {json.dumps(output.extracted, default=str)}"
        self.memory.store(
            key=output.suggested_key,
            content=memory_content,
            context=output.context,
            source_type=output.source,
            relevance=output.importance,
        )
        self._log(f"  💾 Stored '{output.suggested_key}' (relevance: {output.importance:.2f})")

        # Update attention context based on what we just processed
        attention_terms = output.extracted.get("keywords", [])
        if output.extracted.get("categories"):
            attention_terms.extend(output.extracted["categories"])
        if output.extracted.get("label"):
            attention_terms.append(output.extracted["label"])
        if attention_terms:
            self.memory.update_attention(attention_terms)

        # Check for stage advancement
        if self.curriculum.should_advance():
            advanced = self.curriculum.advance()
            if advanced:
                self._log(f"  🎓 ADVANCED to stage {self.curriculum.current_stage.name}!")

        return {
            "status": "processed",
            "output": output.extracted,
            "importance": output.importance,
            "eval_score": eval_score,
            "stage": self.curriculum.current_stage.name,
            "cycle": self.cycle_count,
        }

    def query(self, question: str) -> dict:
        """Ask the system a question based on what it has learned."""
        self._log(f"❓ Query: '{question}'")

        results = self.memory.search(question, top_k=5)

        if not results:
            self._log("  No relevant memories found.")
            return {"answer": "I don't have enough experience to answer that.", "memories_used": 0}

        self._log(f"  Found {len(results)} relevant memories:")
        memories_used = []
        for key, mem in results:
            self._log(f"    • {key}: {mem.context} (relevance: {mem.relevance:.2f})")
            memories_used.append(mem.to_dict() | {"key": key})

        return {
            "answer": f"Based on {len(results)} memories.",
            "memories_used": len(results),
            "relevant_memories": memories_used,
        }

    def run_curriculum(self):
        """Run through the current stage's curriculum."""
        items = self.curriculum.get_curriculum()
        if not items:
            self._log("No curriculum items for current stage.")
            return

        stage_name = self.curriculum.current_stage.name
        print(f"\n{'='*60}")
        print(f"  STAGE: {stage_name}")
        print(f"{'='*60}")

        for i, item in enumerate(items):
            print(f"\n--- Item {i+1}/{len(items)} ---")
            self.process_input(item["type"], item["data"])

        print(f"\n  Stage {stage_name} complete.")
        print(f"  {json.dumps(self.curriculum.status(), indent=2)}")

    def full_status(self) -> dict:
        return {
            "cycles": self.cycle_count,
            "curriculum": self.curriculum.status(),
            "memory": self.memory.stats(),
            "processors": list(self.processors.keys()),
        }
