"""
Genesis Voice — M13.

Genesis generates statements from its own internal state.

No LLM is used. No borrowed language. Every statement is assembled
directly from the relation graph, inference engine, working memory,
and contradiction log. The voice is Genesis's own because the content
comes from Genesis's own processing history.

Statement types (in priority order when expressing spontaneously):
    1. Contradiction — "I have conflicting information about X"
       (contradictions are the most epistemically interesting signal)
    2. Inference — "from what I know, A leads to C through B"
       (novel multi-hop understanding)
    3. Relation — "I have learned that X causes Y"
       (direct observed knowledge)
    4. Attention — "I have been thinking about X"
       (what Genesis is most preoccupied with right now)
    5. Question — "I have encountered X repeatedly but cannot place it"
       (unresolved concepts — the first form of expressed curiosity)
    6. Novel — "I have just encountered something I have not seen before"
       (OOD signal surfaced as a statement)

Spontaneous expression is triggered by internal signals:
    - High wm_delta (input significantly changed working memory)
    - New inference formed connecting previously unrelated concepts
    - Contradiction detected
    - Novel input encountered

The threshold for speaking is calibrated so Genesis speaks roughly
once every N cycles by default — enough to be present, not so often
it becomes noise.
"""

import random
import re
import time
from typing import TYPE_CHECKING, Optional

from output.channel import OutputChannel, TextChannel

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# Relation type → natural language verb phrase
_REL_VERBS: dict[str, str] = {
    "CAUSES":   "causes",
    "CONTROLS": "controls",
    "PREVENTS": "prevents",
    "ENABLES":  "enables",
    "REQUIRES": "requires",
    "IS_A":     "is a type of",
    "PREDATES": "preys on",
    "AFFECTS":  "affects",
    "CONTAINS": "contains",
}

# Approximately 1 in N cycles may produce a spontaneous expression
# (only when triggered by a relevant internal signal)
_DEFAULT_EXPRESSION_RATE: float = 0.15  # 15% chance when triggered


class GenesisVoice:
    """
    Generates and delivers statements from Genesis's internal state.

    Usage:
        voice = GenesisVoice(brain, channel=OutputChannel.best_available())
        voice.express()              # spontaneous statement if triggered
        voice.express(force=True)    # always produce a statement
        voice.respond("wolves")      # respond to a specific concept
        statement = voice.compose()  # generate without sending
    """

    def __init__(
        self,
        brain: "Orchestrator",
        channel: Optional[OutputChannel] = None,
        expression_rate: float = _DEFAULT_EXPRESSION_RATE,
        min_interval: float = 25.0,
        seed: Optional[int] = None,
    ):
        self._brain = brain
        self._channel = channel or TextChannel()
        self._expression_rate = expression_rate
        self._min_interval = min_interval  # hard floor: seconds between any two expressions
        self._rng = random.Random(seed)

        self._last_expressed_at: float = 0.0
        self._expressions_total: int = 0
        self._last_statement: str = ""

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def express(self, force: bool = False, trigger: Optional[str] = None) -> Optional[str]:
        """
        Produce a spontaneous statement if the internal state warrants it.

        trigger: one of 'novel', 'inference', 'contradiction', 'attention', None
        force: bypass the time gate and probability check

        Returns the statement string if one was produced, None otherwise.
        """
        now = time.time()
        if not force and (now - self._last_expressed_at) < self._min_interval:
            return None
        if not force and self._rng.random() > self._expression_rate:
            return None

        statement = self._compose_for_trigger(trigger)
        if not statement:
            return None

        # Don't repeat the same thing twice in a row
        if not force and statement == self._last_statement:
            return None

        self._deliver(statement)
        return statement

    def respond(self, concept: str) -> Optional[str]:
        """
        Produce a statement specifically about a concept Genesis knows.

        Used when a human names a concept and Genesis responds with
        what it actually knows — not a lookup, but an expression.
        """
        statement = self._compose_about(concept)
        if statement:
            self._deliver(statement)
        return statement

    def chat_respond(self, user_text: str) -> str:
        """
        Receive user input, learn from it, and produce a conversational reply.

        Genesis does two things simultaneously:
          1. Processes the text as new knowledge (always learns from conversation)
          2. Searches its existing knowledge for what it knows about the concepts
             mentioned, and replies from that — not from a template, from its
             actual processing history.

        Returns a non-empty response string.
        """
        # Learn from what was said
        result = self._brain.process_input("text", user_text)
        novel   = result.get("novel", False)
        wm_delta = result.get("wm_delta", 0)

        # Extract concepts the user mentioned, prioritising ones Genesis already knows
        concepts = self._extract_input_concepts(user_text)

        parts: list[str] = []

        # Acknowledge genuinely new input
        if novel and wm_delta > 0 and not concepts:
            parts.append("That's new to me. I've taken it in.")

        # Reply about each concept mentioned (up to 2)
        responded: set[str] = set()
        for concept in concepts[:2]:
            if concept in responded:
                continue
            responded.add(concept)

            # Inferences are the most interesting thing to share
            inf = self._brain.inference.query(concept)
            if inf["as_subject"]:
                entry = inf["as_subject"][0]
                verb = _REL_VERBS.get(entry["relation"], entry["relation"].lower())
                obj  = entry["object"].replace("_", " ")
                parts.append(
                    f"I've worked out that {concept} {verb} {obj} — "
                    f"I arrived at that across {entry['chain_length']} step(s)."
                )
                continue

            # Direct relations
            outgoing = self._brain.relations.query_subject(concept, min_confidence=0.5)
            if outgoing:
                rel  = self._rng.choice(outgoing[:3])
                verb = _REL_VERBS.get(rel["relation"], rel["relation"].lower())
                obj  = rel["object"].replace("_", " ")
                parts.append(f"I know that {concept} {verb} {obj}.")
            else:
                # Genesis has heard of it but knows little
                parts.append(
                    f"I've come across {concept} before, "
                    f"but I haven't formed strong connections around it yet."
                )

        # Add a curiosity question to keep the exchange going (randomised gap)
        if len(parts) < 2:
            curiosity = self._brain.curiosity_report()
            gaps = [c for c in curiosity if not c.get("already_fetched")]
            if gaps:
                pick = self._rng.choice(gaps[:5])
                topic = pick["concept"]
                parts.append(
                    f"I'm still trying to understand {topic}. "
                    f"Do you know anything about it?"
                )

        if not parts:
            # Last resort: share whatever is most salient right now
            stmt = self._compose_for_trigger(None)
            return stmt or "I'm processing what you've said — my understanding is still forming."

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Concept extraction helper
    # ------------------------------------------------------------------

    def _extract_input_concepts(self, text: str) -> list[str]:
        """
        Extract concepts from user text that Genesis already has knowledge about.

        Only returns words that exist in the relation graph as subject or object.
        Unknown words are ignored — saying "I've come across 'tell' before" when
        the user typed "tell me about it" is meaningless and confusing.
        """
        try:
            from ingestion.curiosity import _SKIP_CONCEPTS, _MIN_CONCEPT_LEN
        except ImportError:
            _SKIP_CONCEPTS = set()
            _MIN_CONCEPT_LEN = 4

        words = re.findall(r'\b[a-z]{4,}\b', text.lower())
        meaningful = [w for w in words if w not in _SKIP_CONCEPTS]

        if not meaningful:
            return []

        # Only surface concepts Genesis actually knows — avoids "I've come across
        # 'tell' before" when the user typed "tell me about it"
        conn = self._brain.relations._conn
        known: list[str] = []
        seen: set[str] = set()
        for word in meaningful:
            if word in seen:
                continue
            seen.add(word)
            row = conn.execute(
                "SELECT 1 FROM relations WHERE subject = ? OR object = ? LIMIT 1",
                (word, word)
            ).fetchone()
            if row:
                known.append(word)
        return known[:5]

    def compose(self, trigger: Optional[str] = None) -> Optional[str]:
        """Generate a statement without delivering it."""
        return self._compose_for_trigger(trigger)

    # ------------------------------------------------------------------
    # Statement composition
    # ------------------------------------------------------------------

    def _compose_for_trigger(self, trigger: Optional[str]) -> Optional[str]:
        """
        Choose the most appropriate statement type given the trigger.
        """
        composers = {
            "contradiction": self._compose_contradiction,
            "inference":     self._compose_inference,
            "novel":         self._compose_novel,
            "attention":     self._compose_attention,
        }

        if trigger and trigger in composers:
            stmt = composers[trigger]()
            if stmt:
                return stmt

        # Default: try each type in priority order
        for fn in [
            self._compose_contradiction,
            self._compose_inference,
            self._compose_relation,
            self._compose_attention,
            self._compose_question,
        ]:
            stmt = fn()
            if stmt:
                return stmt

        return None

    def _compose_contradiction(self) -> Optional[str]:
        """Express a known contradiction."""
        conflicts = self._brain.contradictions.query(limit=20)
        if not conflicts:
            return None
        conflict = self._rng.choice(conflicts[:5])
        subj = conflict["subject"].replace("_", " ")
        obj = conflict["object"].replace("_", " ")
        verb_a = _REL_VERBS.get(conflict["rel_type_a"], conflict["rel_type_a"].lower())
        verb_b = _REL_VERBS.get(conflict["rel_type_b"], conflict["rel_type_b"].lower())
        return (
            f"I have conflicting information about {subj}. "
            f"It has been described as something that {verb_a} {obj}, "
            f"but also as something that {verb_b} {obj}. "
            f"I don't know which is true."
        )

    def _compose_inference(self) -> Optional[str]:
        """Express a transitive inference Genesis has derived."""
        top = self._brain.inference.top_inferences(limit=20)
        if not top:
            return None
        entry = self._rng.choice(top[:8])
        chain = self._brain.inference.chain_for(
            entry["subject"], entry["relation"], entry["object"]
        )
        subj = entry["subject"].replace("_", " ")
        obj = entry["object"].replace("_", " ")
        verb = _REL_VERBS.get(entry["relation"], entry["relation"].lower())

        if chain and len(chain) >= 2:
            middle = chain[len(chain) // 2]["to"].replace("_", " ")
            return (
                f"From what I have processed, it seems that {subj} {verb} {obj}. "
                f"The connection runs through {middle}."
            )
        return f"I have derived that {subj} {verb} {obj}."

    def _compose_relation(self) -> Optional[str]:
        """Express a directly observed high-confidence relation."""
        most_connected = self._brain.relations.most_connected(limit=10)
        if not most_connected:
            return None
        concept = self._rng.choice(most_connected[:5])["concept"]
        outgoing = self._brain.relations.query_subject(concept, min_confidence=0.7)
        if not outgoing:
            return None
        rel = self._rng.choice(outgoing[:5])
        subj = concept.replace("_", " ")
        obj = rel["object"].replace("_", " ")
        verb = _REL_VERBS.get(rel["relation"], rel["relation"].lower())
        return f"I have learned that {subj} {verb} {obj}."

    def _compose_attention(self) -> Optional[str]:
        """Express what Genesis is most preoccupied with right now."""
        wm = self._brain.memory.memories
        if not wm:
            return None
        top = sorted(wm.items(), key=lambda kv: kv[1].relevance, reverse=True)
        if not top:
            return None
        key, mem = top[0]
        # Extract readable concept from key
        concept = re.sub(r"^[a-z]+:", "", key).replace("_", " ").strip()
        if not concept:
            return None
        snippet = mem.context[:60].rstrip()
        return f"I have been thinking about {concept}. {snippet}."

    def _compose_question(self) -> Optional[str]:
        """Express curiosity about an unresolved concept."""
        wm = self._brain.memory.memories
        if not wm:
            return None
        # Unresolved = low relevance despite being in working memory
        low_relevance = [
            (k, m) for k, m in wm.items()
            if m.relevance < 0.3 and len(self._brain.relations.query_concept(
                re.sub(r"^[a-z]+:", "", k), min_confidence=0.5
            )["as_subject"]) == 0
        ]
        if not low_relevance:
            return None
        key, _ = self._rng.choice(low_relevance[:10])
        concept = re.sub(r"^[a-z]+:", "", key).replace("_", " ").strip()
        if not concept:
            return None
        return (
            f"I have encountered {concept} a number of times "
            f"but I have not been able to form a clear understanding of it."
        )

    def _compose_novel(self) -> Optional[str]:
        """Express encounter with something genuinely unfamiliar."""
        # Once Genesis has real knowledge, fall through to more informative types
        if self._brain.relations.most_connected(limit=1):
            return None
        return (
            "I have just processed something I have not encountered before. "
            "I don't yet know what to make of it."
        )

    def _compose_about(self, concept: str) -> Optional[str]:
        """Compose a statement specifically about a named concept."""
        norm = concept.lower().strip()

        # Check contradictions first
        conflicts = self._brain.contradictions.query_concept(norm)
        if conflicts:
            c = conflicts[0]
            verb_a = _REL_VERBS.get(c["rel_type_a"], c["rel_type_a"].lower())
            verb_b = _REL_VERBS.get(c["rel_type_b"], c["rel_type_b"].lower())
            return (
                f"I have conflicting information about {norm}. "
                f"It {verb_a} {c['object'].replace('_', ' ')}, "
                f"but it also {verb_b} {c['object'].replace('_', ' ')}."
            )

        # Check inferences
        inf = self._brain.inference.query(norm)
        if inf["as_subject"]:
            entry = inf["as_subject"][0]
            verb = _REL_VERBS.get(entry["relation"], entry["relation"].lower())
            obj = entry["object"].replace("_", " ")
            return (
                f"From what I have processed, {norm} appears to {verb} {obj}. "
                f"I derived this across {entry['chain_length']} steps."
            )

        # Fall back to direct relations
        outgoing = self._brain.relations.query_subject(norm, min_confidence=0.5)
        if outgoing:
            rel = outgoing[0]
            verb = _REL_VERBS.get(rel["relation"], rel["relation"].lower())
            obj = rel["object"].replace("_", " ")
            return f"I have learned that {norm} {verb} {obj}."

        return f"I have encountered {norm} but have not formed strong connections around it yet."

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    def _deliver(self, statement: str) -> None:
        self._last_statement = statement
        self._last_expressed_at = time.time()
        self._expressions_total += 1
        try:
            self._channel.send(statement)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def set_channel(self, channel: OutputChannel) -> None:
        """Switch output channel."""
        self._channel = channel

    @property
    def channel_name(self) -> str:
        return self._channel.name

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        return {
            "expressions_total": self._expressions_total,
            "last_expressed_at": self._last_expressed_at,
            "last_statement":    self._last_statement[:80] if self._last_statement else "",
            "channel":           self._channel.name,
            "expression_rate":   self._expression_rate,
        }
