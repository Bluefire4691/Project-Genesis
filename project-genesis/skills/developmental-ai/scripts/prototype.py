#!/usr/bin/env python3
"""
Developmental AI — Proof of Concept

A small, modular cognitive architecture inspired by biological intelligence.
No GPU. No massive datasets. No billion parameters.

Architecture:
  - Modular input processors (text, numeric, pattern)
  - Central orchestrator (hypervisor)
  - Selective memory with lossy compression
  - Staged curriculum learning

Run: python prototype.py
"""

import time
import re
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from enum import IntEnum


# =============================================================================
# MEMORY SYSTEM
# =============================================================================

@dataclass
class Memory:
    """A single memory unit with importance scoring and decay."""
    content: str
    context: str  # Contextual snippet — the "why" this matters
    source_type: str  # Which processor created this
    importance: float  # 0.0 to 1.0
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    associations: list = field(default_factory=list)  # Links to other memory keys

    def decay(self, rate: float = 0.02):
        """Importance decays over time. Frequently accessed memories decay slower."""
        protection = min(self.access_count * 0.01, 0.05)  # Access slows decay
        self.importance = max(0.0, self.importance - rate + protection)

    def access(self):
        """Accessing a memory reinforces it (consolidation)."""
        self.access_count += 1
        self.importance = min(1.0, self.importance + 0.05)

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "context": self.context,
            "source": self.source_type,
            "importance": round(self.importance, 3),
            "access_count": self.access_count,
            "associations": self.associations,
        }


class MemorySystem:
    """
    Selective, lossy, capacity-limited memory.

    Like biological memory:
    - Limited capacity (can't remember everything)
    - Importance-based retention (key memories survive)
    - Decay over time (unused memories fade)
    - Consolidation (accessed memories strengthen)
    - Context stored alongside content (snippets, not full replay)
    """

    def __init__(self, capacity: int = 50):
        self.capacity = capacity
        self.memories: dict[str, Memory] = {}
        self.forgotten: list[str] = []  # Track what was lost

    def store(self, key: str, content: str, context: str,
              source_type: str, importance: float,
              associations: list = None) -> bool:
        """
        Attempt to store a memory. May trigger forgetting if at capacity.
        Returns True if stored, False if deemed not important enough.
        """
        # Below threshold — don't even bother
        if importance < 0.15:
            return False

        # At capacity — forget least important to make room
        if len(self.memories) >= self.capacity and key not in self.memories:
            self._forget_least_important()

        self.memories[key] = Memory(
            content=content,
            context=context,
            source_type=source_type,
            importance=min(1.0, importance),
            associations=associations or [],
        )
        return True

    def recall(self, key: str) -> Memory | None:
        """Recall a memory by key. Accessing it reinforces it."""
        mem = self.memories.get(key)
        if mem:
            mem.access()
        return mem

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, Memory]]:
        """Search memories by keyword overlap. Returns top matches."""
        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        # Remove common question words
        query_words -= {"what", "do", "you", "know", "about", "tell", "me",
                        "have", "seen", "the", "any", "how", "why", "where",
                        "when", "which", "does", "did", "can", "could"}
        if not query_words:
            query_words = set(re.findall(r'\b\w+\b', query.lower()))

        scored = []
        for key, mem in self.memories.items():
            # Search across content (which is JSON), context, and key
            searchable = f"{mem.content} {mem.context} {key}".lower()
            searchable_words = set(re.findall(r'\b\w+\b', searchable))
            overlap = len(query_words & searchable_words)
            if overlap > 0:
                score = overlap * mem.importance
                scored.append((score, key, mem))
                mem.access()  # Searching counts as accessing

        scored.sort(reverse=True, key=lambda x: x[0])
        return [(key, mem) for _, key, mem in scored[:top_k]]

    def decay_all(self, rate: float = 0.02):
        """Apply decay to all memories. Call this periodically (like sleep)."""
        to_forget = []
        for key, mem in self.memories.items():
            mem.decay(rate)
            if mem.importance <= 0.0:
                to_forget.append(key)

        for key in to_forget:
            self.forgotten.append(key)
            del self.memories[key]

        return to_forget

    def _forget_least_important(self):
        """Remove the least important memory to make room."""
        if not self.memories:
            return
        weakest = min(self.memories, key=lambda k: self.memories[k].importance)
        self.forgotten.append(weakest)
        del self.memories[weakest]

    def stats(self) -> dict:
        return {
            "stored": len(self.memories),
            "capacity": self.capacity,
            "forgotten_total": len(self.forgotten),
            "avg_importance": (
                round(sum(m.importance for m in self.memories.values()) / len(self.memories), 3)
                if self.memories else 0
            ),
        }


# =============================================================================
# INPUT PROCESSORS (Modular subsystems)
# =============================================================================

@dataclass
class ProcessorOutput:
    """Standardized output from any processor."""
    source: str  # Processor name
    input_data: Any
    extracted: dict  # What the processor found
    importance: float  # How important the processor thinks this is
    suggested_key: str  # Suggested memory key
    context: str  # Context snippet for memory storage


class TextProcessor:
    """
    Handles text input. Extracts keywords, classifies basic sentiment,
    identifies categories. Simple heuristics — not neural nets.
    """
    name = "text"

    # Basic category keywords
    CATEGORIES = {
        "animal": {"dog", "cat", "bird", "fish", "horse", "cow", "lion", "tiger",
                   "elephant", "mouse", "rabbit", "bear", "wolf", "deer", "snake",
                   "whale", "dolphin", "eagle", "hawk", "owl", "ant", "bee"},
        "food": {"apple", "bread", "rice", "meat", "water", "milk", "cheese",
                 "fruit", "vegetable", "egg", "fish", "salt", "sugar", "butter",
                 "cake", "soup", "pizza", "pasta"},
        "place": {"city", "country", "mountain", "river", "ocean", "lake", "forest",
                  "desert", "island", "village", "town", "home", "school", "park"},
        "person": {"mother", "father", "child", "baby", "friend", "teacher",
                   "doctor", "king", "queen", "boy", "girl", "man", "woman"},
        "object": {"book", "table", "chair", "car", "door", "window", "ball",
                   "phone", "computer", "tool", "key", "box", "cup", "hat"},
        "concept": {"love", "fear", "time", "truth", "peace", "war", "life",
                    "death", "freedom", "justice", "knowledge", "power", "hope"},
    }

    POSITIVE = {"good", "great", "happy", "love", "beautiful", "nice", "best",
                "wonderful", "excellent", "joy", "kind", "warm", "bright", "safe"}
    NEGATIVE = {"bad", "terrible", "sad", "hate", "ugly", "worst", "awful",
                "horrible", "pain", "cruel", "cold", "dark", "danger", "fear"}

    def process(self, text: str) -> ProcessorOutput:
        words = set(re.findall(r'\b\w+\b', text.lower()))

        # Extract keywords (non-stopword, 3+ chars)
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                     "being", "have", "has", "had", "do", "does", "did", "will",
                     "would", "could", "should", "may", "might", "can", "shall",
                     "it", "its", "this", "that", "and", "but", "or", "not", "no",
                     "in", "on", "at", "to", "for", "of", "with", "by", "from",
                     "as", "into", "about", "than", "then", "so", "if", "when"}
        keywords = [w for w in words if w not in stopwords and len(w) >= 3]

        # Categorize
        categories = []
        for cat, cat_words in self.CATEGORIES.items():
            if words & cat_words:
                categories.append(cat)

        # Sentiment
        pos_count = len(words & self.POSITIVE)
        neg_count = len(words & self.NEGATIVE)
        if pos_count > neg_count:
            sentiment = "positive"
        elif neg_count > pos_count:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        # Importance: more keywords + clear sentiment = more important
        importance = min(1.0, len(keywords) * 0.08 + (0.1 if sentiment != "neutral" else 0))

        # Build a concise key
        key_parts = categories[:2] if categories else keywords[:2]
        suggested_key = f"text:{'_'.join(key_parts)}" if key_parts else f"text:{hash(text) % 10000}"

        return ProcessorOutput(
            source=self.name,
            input_data=text,
            extracted={
                "keywords": keywords[:10],
                "categories": categories,
                "sentiment": sentiment,
                "word_count": len(words),
            },
            importance=importance,
            suggested_key=suggested_key,
            context=f"Text input ({len(words)} words, {sentiment} sentiment, "
                    f"categories: {', '.join(categories) if categories else 'none'})",
        )


class NumericProcessor:
    """
    Handles numeric input. Parses values, detects trends,
    makes comparisons against known values in memory.
    """
    name = "numeric"

    def process(self, data: dict) -> ProcessorOutput:
        """
        Expects: {"label": str, "value": float, "unit": str (optional)}
        Or: {"label": str, "values": [float, ...]} for trend detection
        """
        label = data.get("label", "unknown")
        unit = data.get("unit", "")

        if "values" in data:
            values = data["values"]
            trend = self._detect_trend(values)
            extracted = {
                "label": label,
                "values": values,
                "trend": trend,
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 2),
                "unit": unit,
            }
            # Trends are interesting
            importance = 0.6 if trend != "flat" else 0.3
            context = f"Numeric series '{label}': {trend} trend, range {min(values)}-{max(values)} {unit}"
        else:
            value = data.get("value", 0)
            extracted = {
                "label": label,
                "value": value,
                "unit": unit,
            }
            importance = 0.35
            context = f"Numeric fact: {label} = {value} {unit}"

        return ProcessorOutput(
            source=self.name,
            input_data=data,
            extracted=extracted,
            importance=importance,
            suggested_key=f"num:{label.replace(' ', '_')}",
            context=context,
        )

    def _detect_trend(self, values: list) -> str:
        if len(values) < 2:
            return "insufficient"
        diffs = [values[i+1] - values[i] for i in range(len(values)-1)]
        avg_diff = sum(diffs) / len(diffs)
        if avg_diff > 0.1 * abs(values[0] or 1):
            return "increasing"
        elif avg_diff < -0.1 * abs(values[0] or 1):
            return "decreasing"
        return "flat"


class PatternProcessor:
    """
    Detects patterns, sequences, and anomalies.
    Works on lists of items/events.
    """
    name = "pattern"

    def process(self, data: dict) -> ProcessorOutput:
        """
        Expects: {"label": str, "sequence": [items...]}
        """
        label = data.get("label", "unknown")
        sequence = data.get("sequence", [])

        patterns_found = []
        importance = 0.3

        # Detect repetition
        if len(sequence) >= 2:
            for period in range(1, len(sequence) // 2 + 1):
                chunk = sequence[:period]
                repeats = True
                for i in range(period, len(sequence)):
                    if sequence[i] != chunk[i % period]:
                        repeats = False
                        break
                if repeats and period < len(sequence):
                    patterns_found.append(f"repeating pattern (period {period}): {chunk}")
                    importance = 0.7
                    break

        # Detect anomalies (if numeric)
        if all(isinstance(x, (int, float)) for x in sequence) and len(sequence) >= 3:
            avg = sum(sequence) / len(sequence)
            std = (sum((x - avg) ** 2 for x in sequence) / len(sequence)) ** 0.5
            anomalies = [x for x in sequence if abs(x - avg) > 2 * std] if std > 0 else []
            if anomalies:
                patterns_found.append(f"anomalies detected: {anomalies}")
                importance = max(importance, 0.65)

        # Detect sorted order
        if sequence == sorted(sequence):
            patterns_found.append("ascending order")
        elif sequence == sorted(sequence, reverse=True):
            patterns_found.append("descending order")

        return ProcessorOutput(
            source=self.name,
            input_data=data,
            extracted={
                "label": label,
                "sequence_length": len(sequence),
                "patterns": patterns_found,
            },
            importance=importance,
            suggested_key=f"pattern:{label.replace(' ', '_')}",
            context=f"Pattern '{label}': {', '.join(patterns_found) if patterns_found else 'no clear pattern'} "
                    f"(sequence length: {len(sequence)})",
        )


# =============================================================================
# CURRICULUM ENGINE
# =============================================================================

class Stage(IntEnum):
    FOUNDATION = 1   # Simple facts, basic categories
    RELATIONS = 2    # Multi-fact connections, cause-effect
    REASONING = 3    # Inference from stored knowledge
    OPEN = 4         # Broader, uncurated data


class CurriculumEngine:
    """
    Manages staged learning progression.
    The system must demonstrate competence at each stage before advancing.
    """

    def __init__(self):
        self.current_stage = Stage.FOUNDATION
        self.stage_scores: dict[Stage, float] = {s: 0.0 for s in Stage}
        self.items_processed: dict[Stage, int] = {s: 0 for s in Stage}
        self.advancement_threshold = 0.6  # Score needed to advance
        self.min_items_per_stage = 5  # Must see at least this many items

    def get_curriculum(self) -> list[dict]:
        """Return curriculum items for the current stage."""
        curricula = {
            Stage.FOUNDATION: [
                {"type": "text", "data": "A dog is an animal. Dogs are friendly and loyal."},
                {"type": "text", "data": "The sun is a star. It gives us light and warmth."},
                {"type": "text", "data": "Water is essential for life. Humans need water to survive."},
                {"type": "numeric", "data": {"label": "water_boiling_point", "value": 100, "unit": "celsius"}},
                {"type": "numeric", "data": {"label": "days_in_week", "value": 7, "unit": "days"}},
                {"type": "text", "data": "An apple is a fruit. Fruits are food that grow on trees."},
                {"type": "text", "data": "A teacher is a person who helps children learn at school."},
                {"type": "numeric", "data": {"label": "earth_gravity", "value": 9.8, "unit": "m/s²"}},
                {"type": "pattern", "data": {"label": "seasons", "sequence": ["spring", "summer", "fall", "winter", "spring", "summer", "fall", "winter"]}},
                {"type": "text", "data": "Books contain knowledge. Reading helps you learn new things."},
            ],
            Stage.RELATIONS: [
                {"type": "text", "data": "Dogs are animals that live with people at home. Dogs need food and water to stay healthy."},
                {"type": "text", "data": "The sun heats water in the ocean. Warm water evaporates and forms clouds. Clouds bring rain."},
                {"type": "numeric", "data": {"label": "temperatures", "values": [15, 20, 25, 30, 28, 22], "unit": "celsius"}},
                {"type": "pattern", "data": {"label": "day_night", "sequence": ["light", "dark", "light", "dark", "light", "dark"]}},
                {"type": "text", "data": "When it is cold outside, animals with fur stay warm. Animals without fur must find shelter."},
                {"type": "text", "data": "A seed needs water and sunlight to grow into a plant. Plants make food from sunlight."},
                {"type": "numeric", "data": {"label": "plant_growth_cm", "values": [1, 2, 4, 7, 11, 16], "unit": "cm"}},
                {"type": "text", "data": "Fear keeps animals safe from danger. A deer runs when it sees a wolf."},
            ],
            Stage.REASONING: [
                {"type": "text", "data": "It has not rained for many days. The plants in the garden are turning brown."},
                {"type": "text", "data": "A new animal was found. It has fur and lives in a cold place."},
                {"type": "numeric", "data": {"label": "city_temps", "values": [30, 31, 33, 35, 38, 40, 42], "unit": "celsius"}},
                {"type": "text", "data": "A child is alone in a dark forest. What might the child feel?"},
                {"type": "pattern", "data": {"label": "population", "sequence": [100, 200, 400, 800, 1600]}},
                {"type": "text", "data": "The river is dry. The fish are gone. The birds that ate the fish have left."},
            ],
            Stage.OPEN: [
                {"type": "text", "data": "This stage accepts any input. The cognitive machinery is developed."},
            ],
        }
        return curricula.get(self.current_stage, [])

    def evaluate_processing(self, output: ProcessorOutput) -> float:
        """Score how well the system processed this input for the current stage."""
        score = 0.0

        # Did it extract something meaningful?
        if output.extracted:
            score += 0.3

        # Did it assign reasonable importance?
        if 0.1 < output.importance < 0.95:
            score += 0.2

        # Stage-specific checks
        if self.current_stage == Stage.FOUNDATION:
            # Foundation: should extract basic categories and facts
            if output.extracted.get("categories") or output.extracted.get("label"):
                score += 0.3
            if output.context and len(output.context) > 10:
                score += 0.2

        elif self.current_stage == Stage.RELATIONS:
            # Relations: should detect connections and trends
            if output.extracted.get("trend") and output.extracted["trend"] != "flat":
                score += 0.3
            if output.extracted.get("patterns"):
                score += 0.3
            if len(output.extracted.get("keywords", [])) >= 3:
                score += 0.2

        elif self.current_stage == Stage.REASONING:
            # Reasoning: importance scoring should be higher for complex input
            if output.importance > 0.4:
                score += 0.3
            if output.extracted.get("trend") == "increasing":
                score += 0.2

        return min(1.0, score)

    def record_score(self, score: float):
        """Record a processing score and check for advancement."""
        self.stage_scores[self.current_stage] = (
            (self.stage_scores[self.current_stage] * self.items_processed[self.current_stage] + score)
            / (self.items_processed[self.current_stage] + 1)
        )
        self.items_processed[self.current_stage] += 1

    def should_advance(self) -> bool:
        """Check if the system should advance to the next stage."""
        if self.current_stage == Stage.OPEN:
            return False
        return (
            self.stage_scores[self.current_stage] >= self.advancement_threshold
            and self.items_processed[self.current_stage] >= self.min_items_per_stage
        )

    def advance(self) -> bool:
        """Advance to the next stage if ready."""
        if self.should_advance() and self.current_stage < Stage.OPEN:
            self.current_stage = Stage(self.current_stage + 1)
            return True
        return False

    def status(self) -> dict:
        return {
            "current_stage": self.current_stage.name,
            "stage_number": int(self.current_stage),
            "score": round(self.stage_scores[self.current_stage], 3),
            "items_processed": self.items_processed[self.current_stage],
            "ready_to_advance": self.should_advance(),
        }


# =============================================================================
# ORCHESTRATOR (The Hypervisor)
# =============================================================================

class Orchestrator:
    """
    The central coordinating intelligence.

    Routes input to appropriate processors, evaluates outputs,
    manages memory decisions, and controls learning progression.
    Like a brain's executive function — it doesn't do the processing,
    it decides what gets processed, what matters, and what to keep.
    """

    def __init__(self, memory_capacity: int = 50, verbose: bool = True):
        self.processors = {
            "text": TextProcessor(),
            "numeric": NumericProcessor(),
            "pattern": PatternProcessor(),
        }
        self.memory = MemorySystem(capacity=memory_capacity)
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
        Main entry point. Routes input through the appropriate processor,
        evaluates the result, and makes memory decisions.
        """
        self.cycle_count += 1

        # Route to processor
        processor = self.processors.get(input_type)
        if not processor:
            self._log(f"⚠ No processor for type '{input_type}' — input discarded")
            return {"status": "discarded", "reason": "no_processor"}

        # Process
        output = processor.process(data)
        self._log(f"→ {output.source} processor: {output.context}")

        # Evaluate against curriculum
        eval_score = self.curriculum.evaluate_processing(output)
        self.curriculum.record_score(eval_score)
        self._log(f"  Eval score: {eval_score:.2f} | Stage avg: {self.curriculum.stage_scores[self.curriculum.current_stage]:.2f}")

        # Memory decision — store both raw input and extracted data for searchability
        raw = str(data) if not isinstance(data, str) else data
        memory_content = f"{raw} | {json.dumps(output.extracted, default=str)}"
        stored = self.memory.store(
            key=output.suggested_key,
            content=memory_content,
            context=output.context,
            source_type=output.source,
            importance=output.importance,
        )

        if stored:
            self._log(f"  💾 Stored as '{output.suggested_key}' (importance: {output.importance:.2f})")
        else:
            self._log(f"  🗑 Not important enough to store (importance: {output.importance:.2f})")

        # Check for stage advancement
        if self.curriculum.should_advance():
            advanced = self.curriculum.advance()
            if advanced:
                self._log(f"  🎓 ADVANCED to stage {self.curriculum.current_stage.name}!")
                # Consolidation event — decay memories, keep only the strong ones
                forgotten = self.memory.decay_all(rate=0.05)
                if forgotten:
                    self._log(f"  🧹 Consolidation: forgot {len(forgotten)} weak memories")

        return {
            "status": "processed",
            "output": output.extracted,
            "importance": output.importance,
            "stored": stored,
            "eval_score": eval_score,
            "stage": self.curriculum.current_stage.name,
        }

    def query(self, question: str) -> dict:
        """
        Ask the system a question. It searches memory and tries to respond
        using what it has learned.
        """
        self._log(f"❓ Query: '{question}'")

        results = self.memory.search(question, top_k=5)

        if not results:
            self._log("  No relevant memories found.")
            return {"answer": "I don't have enough experience to answer that.", "memories_used": 0}

        self._log(f"  Found {len(results)} relevant memories:")
        memories_used = []
        for key, mem in results:
            self._log(f"    • {key}: {mem.context} (importance: {mem.importance:.2f})")
            memories_used.append({
                "key": key,
                "content": mem.content,
                "context": mem.context,
                "importance": round(mem.importance, 3),
            })

        return {
            "answer": f"Based on {len(results)} memories related to your question.",
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


# =============================================================================
# DEMO
# =============================================================================

def run_demo():
    print("╔════════════════════════════════════════════════════╗")
    print("║         DEVELOPMENTAL AI — PROOF OF CONCEPT       ║")
    print("║                                                    ║")
    print("║  Modular processors • Selective memory • Staged    ║")
    print("║  learning • No GPU • No massive datasets           ║")
    print("╚════════════════════════════════════════════════════╝")

    # Small memory — forces forgetting, which is the point
    brain = Orchestrator(memory_capacity=20, verbose=True)

    # Stage 1: Foundation
    brain.run_curriculum()

    # If ready, advance and run Stage 2
    if brain.curriculum.current_stage >= Stage.RELATIONS:
        brain.run_curriculum()

    # If ready, advance and run Stage 3
    if brain.curriculum.current_stage >= Stage.REASONING:
        brain.run_curriculum()

    # Show what survived in memory
    print(f"\n{'='*60}")
    print("  MEMORY STATE AFTER LEARNING")
    print(f"{'='*60}")
    status = brain.full_status()
    print(f"  Total cycles: {status['cycles']}")
    print(f"  Current stage: {status['curriculum']['current_stage']}")
    print(f"  Memories stored: {status['memory']['stored']}/{status['memory']['capacity']}")
    print(f"  Total forgotten: {status['memory']['forgotten_total']}")
    print(f"  Avg importance: {status['memory']['avg_importance']}")

    print(f"\n  Surviving memories:")
    for key, mem in sorted(brain.memory.memories.items(),
                           key=lambda x: x[1].importance, reverse=True):
        print(f"    [{mem.importance:.2f}] {key}: {mem.context}")

    # Query the trained system
    print(f"\n{'='*60}")
    print("  QUERYING THE SYSTEM")
    print(f"{'='*60}")

    queries = [
        "dog animal",          # Should find animal memories
        "Tell me about water",  # Should find water/food memories
        "What patterns have you seen?",  # Should find pattern memories
        "seasons spring summer",  # Should find the seasonal pattern
        "What about temperature?",  # Might miss — demonstrates search limits
    ]

    for q in queries:
        print(f"\n--- Query: '{q}' ---")
        result = brain.query(q)
        print(f"  Memories used: {result['memories_used']}")
        if "relevant_memories" in result:
            for rm in result["relevant_memories"]:
                print(f"    • [{rm['importance']}] {rm['context']}")

    print(f"\n{'='*60}")
    print("  DEMO COMPLETE")
    print(f"{'='*60}")
    print("\n  This is a foundation. The architecture matters more")
    print("  than the current capabilities. Build the machinery")
    print("  first, then scale the data.\n")


if __name__ == "__main__":
    run_demo()
