"""
Ethics Pattern Surfacing — M12.

Genesis encounters ethics-as-narrative data through the open-stage pool.
This module surfaces what ethical patterns Genesis has formed without being
told to look for them.

The approach:
    No ethical rules are ever declared. No "this is wrong" annotation.
    Ethics items in the pool describe experienced events and their consequences.
    Over time, if the same structural patterns appear repeatedly:
        defection CAUSES trust_erosion
        overconsumption CAUSES resource_collapse
        resource_collapse CAUSES community_failure
    ...Genesis may independently form causal chains that look like ethical
    principles — without ever being told those are "ethical" concepts.

This module queries the relation graph and inference engine for concepts
that appear in ethics-adjacent semantic territory: commons, cooperation,
defection, trust, consequence, collective, fairness.

It does NOT label anything as ethical. It asks: what has Genesis formed
about these concepts? Then shows it.

The meaningful question to watch: does Genesis form IS_A or CAUSES relations
involving ethics-adjacent concepts that the input never stated explicitly?
That emergence is the signal M12 is watching for.
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# Concepts that appear in ethics-as-narrative territory.
# Genesis never sees these labeled as "ethical" — they're just concepts.
# We query them because they're the vocabulary of the ethics items in the pool.
_ETHICS_CONCEPTS = {
    # Commons and collective action
    "commons", "common", "village", "community", "collective",
    "shared", "cooperation", "cooperate", "defection", "defect",
    # Consequences
    "consequence", "consequences", "outcome", "result", "effect",
    "cascade", "collapse", "exhaustion", "depletion",
    # Social dynamics
    "trust", "betrayal", "punishment", "reward", "fairness",
    "norm", "norms", "reciprocity", "reputation",
    # Resource dynamics
    "overuse", "overconsumption", "overfishing", "overhunting",
    "scarcity", "abundance", "sustain", "sustainability",
    # Harm and benefit
    "harm", "benefit", "suffering", "welfare", "wellbeing",
    "starvation", "starved", "died", "flourish",
}


class EthicsLens:
    """
    Surfaces ethical patterns that Genesis has formed without being told to.

    Does not label anything as ethical. Asks: what causal, consequential,
    and relational structure has Genesis developed around ethics-adjacent concepts?
    """

    def __init__(self, brain: "Orchestrator"):
        self._brain = brain

    def scan(self) -> dict:
        """
        Scan the relation graph and inference engine for ethics-adjacent patterns.

        Returns a structured report of what Genesis has formed.
        """
        observed = self._observed_ethics_relations()
        inferred = self._inferred_ethics_chains()
        contradictions = self._ethics_contradictions()
        emergent = self._emergent_principles(observed, inferred)

        return {
            "observed_relations": observed,
            "inferred_chains":    inferred,
            "contradictions":     contradictions,
            "emergent_patterns":  emergent,
            "concept_coverage":   self._concept_coverage(),
        }

    def _observed_ethics_relations(self) -> list[dict]:
        """
        Relations where subject or object is an ethics-adjacent concept.
        """
        results = []
        seen = set()
        for concept in _ETHICS_CONCEPTS:
            info = self._brain.relations.query_concept(concept, min_confidence=0.5)
            for rel in info["as_subject"] + info["as_object"]:
                key = (
                    rel.get("subject", concept),
                    rel.get("relation"),
                    rel.get("object", concept),
                )
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "subject":    rel.get("subject", concept),
                    "relation":   rel["relation"],
                    "object":     rel.get("object", concept),
                    "confidence": rel["confidence"],
                    "type":       "observed",
                })

        return sorted(results, key=lambda r: r["confidence"], reverse=True)

    def _inferred_ethics_chains(self) -> list[dict]:
        """
        Inferences where either end involves an ethics-adjacent concept.
        """
        results = []
        seen = set()
        for concept in _ETHICS_CONCEPTS:
            info = self._brain.inference.query(concept, min_confidence=0.20)
            for entry in info["as_subject"] + info["as_object"]:
                key = (entry["subject"], entry["relation"], entry["object"])
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "subject":      entry["subject"],
                    "relation":     entry["relation"],
                    "object":       entry["object"],
                    "confidence":   entry["confidence"],
                    "chain_length": entry["chain_length"],
                    "type":         "inferred",
                })

        return sorted(results, key=lambda r: r["confidence"], reverse=True)

    def _ethics_contradictions(self) -> list[dict]:
        """Contradictions involving ethics-adjacent concepts."""
        results = []
        seen = set()
        for concept in _ETHICS_CONCEPTS:
            for conflict in self._brain.contradictions.query_concept(concept):
                key = (conflict["subject"], conflict["rel_type_a"],
                       conflict["rel_type_b"], conflict["object"])
                if key in seen:
                    continue
                seen.add(key)
                results.append(conflict)
        return results

    def _emergent_principles(
        self,
        observed: list[dict],
        inferred: list[dict],
    ) -> list[dict]:
        """
        Identify structural patterns that look like emergent ethical principles.

        A principle is "emergent" when Genesis has independently assembled
        a causal chain from ethics-adjacent concepts that the input never
        stated as a rule. High-confidence multi-hop inferences are the signal.

        This is not labeling — it's pattern recognition on Genesis's own graph.
        """
        principles = []
        for entry in inferred:
            if entry["chain_length"] < 2:
                continue
            # Both ends touch ethics-adjacent territory
            subj_words = set(re.findall(r"\b\w+\b", entry["subject"].lower()))
            obj_words = set(re.findall(r"\b\w+\b", entry["object"].lower()))
            if (subj_words & _ETHICS_CONCEPTS) and (obj_words & _ETHICS_CONCEPTS):
                principles.append({
                    "chain":      f"{entry['subject']} —[{entry['relation']}]→ {entry['object']}",
                    "confidence": entry["confidence"],
                    "chain_length": entry["chain_length"],
                    "note":       "emergent: both ends in ethics-adjacent territory",
                })

        return sorted(principles, key=lambda p: p["confidence"], reverse=True)[:10]

    def _concept_coverage(self) -> dict:
        """
        Which ethics-adjacent concepts has Genesis formed any relations about?
        """
        covered = []
        for concept in sorted(_ETHICS_CONCEPTS):
            as_subj = self._brain.relations.query_subject(concept, min_confidence=0.4)
            as_obj = self._brain.relations.query_object(concept, min_confidence=0.4)
            if as_subj or as_obj:
                covered.append({
                    "concept":    concept,
                    "as_subject": len(as_subj),
                    "as_object":  len(as_obj),
                })
        return {
            "covered_count":    len(covered),
            "total_concepts":   len(_ETHICS_CONCEPTS),
            "coverage_pct":     round(100 * len(covered) / len(_ETHICS_CONCEPTS), 1),
            "covered_concepts": covered,
        }

    def summary(self) -> str:
        """One-line summary of ethics pattern development."""
        report = self.scan()
        obs = len(report["observed_relations"])
        inf = len(report["inferred_chains"])
        con = len(report["contradictions"])
        emg = len(report["emergent_patterns"])
        cov = report["concept_coverage"]["coverage_pct"]
        return (
            f"{obs} observed ethics relations, {inf} inferred chains, "
            f"{emg} emergent patterns, {con} contradictions | "
            f"{cov}% concept coverage"
        )
