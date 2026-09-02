"""
LLM text sensory processor — the falsification-test extractor (board item 0.3).

A DROP-IN replacement for `processors.text.TextProcessor`:

  * subclasses `BaseProcessor` (never raises — errors are data)
  * `name = "text"`, so `Orchestrator.processors["text"] = LLMTextProcessor()`
    is the only change needed anywhere in v1
  * returns the same `ProcessorOutput` with the same `extracted` keys
  * emits `extracted["relations"]` in the identical triple shape the
    orchestrator already ingests:
        {"subject": str, "relation": str, "object": str, "confidence": float}

WHAT IS DIFFERENT — and it is the only thing that is different:
relations come from a local LLM over llama.cpp's OpenAI-compatible HTTP API
instead of 30 regexes. Everything else in the output (keywords, categories,
sentiment, entities, claim_type) is computed by the exact same helpers
`text.py` uses, so any measured difference downstream is attributable to the
extractor and nothing else.

    v1 regex output (real examples from the live DB):
        dogs   PREDATES "using smell"
        number IS_A     "symbol that represents"
    Both are non-referential fragments. They can never be the subject of a
    second relation, so no chain can ever form through them. That — not the
    inference engine — is the hypothesis under test.

CANONICALISATION IS THE CRUX. A triple survives only if both ends are short
noun phrases naming an entity or concept:
    - ≤ 4 words, lowercased, no leading article, no possessive tail
    - no clause markers ("that", "which", "is", "are", ...)
    - no trailing preposition ("responsible for", "used to")
    - no finite-verb / participle tail ("represents", "using smell", "called")
Anything else is dropped, not repaired. A dropped triple costs one edge;
a fragment edge poisons every chain that would have run through it.

Relation types are mapped onto v1's existing vocabulary
(`memory.relations.RELATION_TYPES`) exactly. New types are never invented —
`RelationGraph.add()` silently rejects them, so an unmappable predicate is
dropped here where it can be counted.

Environment:
    GENESIS_LLM_URL      llama-server endpoint. Default
                         http://localhost:8080/v1/chat/completions
                         A base URL ("http://host:8080" or ".../v1") is
                         accepted and completed automatically.
    GENESIS_LLM_MODEL    model name to send (llama-server ignores it;
                         default "local-model")
    GENESIS_LLM_TIMEOUT  per-request timeout in seconds (default 90)
    GENESIS_LLM_OFFLINE  "1" forces offline mode — no HTTP is attempted

Offline / dry-run mode returns a valid, degraded ProcessorOutput with zero
relations so the test-suite and the falsification harness run without a model.
"""

import json
import os
import re
from typing import Any, Callable, Optional

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.types import ProcessorOutput
from processors.base import BaseProcessor
from processors.text import (
    _CATEGORIES,
    _NEGATIVE,
    _POSITIVE,
    _STOPWORDS,
    _build_context,
    _classify_claim,
    _extract_entities,
    _split_sentences,
)
from memory.relations import RELATION_TYPES


# ==================================================================
# Configuration
# ==================================================================

_DEFAULT_URL     = "http://localhost:8080/v1/chat/completions"
_DEFAULT_MODEL   = "local-model"
_DEFAULT_TIMEOUT = 90.0

# Same cap TextProcessor applies (`relations[:8]`). Kept identical so the
# two arms of the falsification test are ingested under the same rules.
MAX_RELATIONS = 8

# Longest input chunk sent to the model. Longer inputs are truncated at a
# sentence boundary; the count is reported in extracted["llm_truncated_chars"].
MAX_INPUT_CHARS = 4000

# Model-assigned confidence is clamped into this band. The floor keeps a
# hedging model from emitting edges the graph would treat as noise; the
# ceiling stops it from claiming certainty no single sentence supports.
_CONF_FLOOR = 0.10
_CONF_CEIL  = 0.95
_CONF_DEFAULT = 0.70

# Maximum words allowed in a canonical entity.
MAX_ENTITY_WORDS = 4


# ==================================================================
# Relation vocabulary mapping
#
# Keys are what a model might plausibly emit; values are members of
# RELATION_TYPES. Anything not in here is DROPPED — we never invent a
# relation type, because the graph schema constrains them.
# ==================================================================

_RELATION_ALIASES: dict[str, str] = {
    # identity mappings
    **{t: t for t in RELATION_TYPES},
    # causation
    "CAUSE": "CAUSES", "CAUSED_BY": "", "LEADS_TO": "CAUSES", "LEAD_TO": "CAUSES",
    "RESULTS_IN": "CAUSES", "RESULT_IN": "CAUSES", "PRODUCES": "CAUSES",
    "PRODUCE": "CAUSES", "TRIGGERS": "CAUSES", "TRIGGER": "CAUSES",
    "CREATES": "CAUSES", "GENERATES": "CAUSES", "DRIVES": "CAUSES",
    # control / regulation
    "CONTROL": "CONTROLS", "REGULATES": "CONTROLS", "REGULATE": "CONTROLS",
    "GOVERNS": "CONTROLS", "MANAGES": "CONTROLS", "LIMITS": "CONTROLS",
    "MAINTAINS": "CONTROLS",
    # prevention
    "PREVENT": "PREVENTS", "INHIBITS": "PREVENTS", "INHIBIT": "PREVENTS",
    "BLOCKS": "PREVENTS", "STOPS": "PREVENTS", "SUPPRESSES": "PREVENTS",
    "REDUCES": "PREVENTS", "PROTECTS": "PREVENTS",
    # enablement
    "ENABLE": "ENABLES", "ALLOWS": "ENABLES", "PERMITS": "ENABLES",
    "SUPPORTS": "ENABLES", "FACILITATES": "ENABLES", "PROVIDES": "ENABLES",
    "USED_FOR": "ENABLES", "USED_IN": "ENABLES",
    # dependency
    "REQUIRE": "REQUIRES", "NEEDS": "REQUIRES", "NEED": "REQUIRES",
    "DEPENDS_ON": "REQUIRES", "DEPENDS": "REQUIRES", "RELIES_ON": "REQUIRES",
    # taxonomy
    "ISA": "IS_A", "IS-A": "IS_A", "INSTANCE_OF": "IS_A", "TYPE_OF": "IS_A",
    "KIND_OF": "IS_A", "SUBCLASS_OF": "IS_A", "PART_OF": "IS_A",
    "MEMBER_OF": "IS_A", "IS_PART_OF": "IS_A", "DEFINED_AS": "IS_A",
    # predation
    "PREDATE": "PREDATES", "EATS": "PREDATES", "PREYS_ON": "PREDATES",
    "FEEDS_ON": "PREDATES", "HUNTS": "PREDATES", "CONSUMES": "PREDATES",
    # composition
    "CONTAIN": "CONTAINS", "COMPOSED_OF": "CONTAINS", "CONSISTS_OF": "CONTAINS",
    "COMPRISES": "CONTAINS", "HAS_PART": "CONTAINS", "INCLUDES": "CONTAINS",
    "MADE_OF": "CONTAINS",
    # unspecified effect
    "AFFECT": "AFFECTS", "INFLUENCES": "AFFECTS", "INFLUENCE": "AFFECTS",
    "IMPACTS": "AFFECTS", "ASSOCIATED_WITH": "AFFECTS", "RELATED_TO": "AFFECTS",
    "CORRELATES_WITH": "AFFECTS", "INVOLVED_IN": "AFFECTS",
}
# CAUSED_BY would need the triple reversed; we drop rather than silently flip
# the direction of a causal claim.
_RELATION_ALIASES = {k: v for k, v in _RELATION_ALIASES.items() if v}


def map_relation(raw: Any) -> Optional[str]:
    """
    Map a model-emitted predicate onto v1's RELATION_TYPES.

    Returns the canonical type, or None if the predicate has no exact
    counterpart in the vocabulary (the triple is then dropped — we never
    invent relation types the graph schema does not know).
    """
    if not isinstance(raw, str):
        return None
    key = re.sub(r"[\s\-]+", "_", raw.strip().upper())
    key = re.sub(r"[^A-Z_]", "", key)
    mapped = _RELATION_ALIASES.get(key)
    return mapped if mapped in RELATION_TYPES else None


# ==================================================================
# Entity canonicalisation
# ==================================================================

# Determiners / quantifiers stripped from the head of a phrase.
_LEADING_DROP = frozenset({
    "the", "a", "an", "this", "that", "these", "those", "its", "their",
    "his", "her", "our", "your", "my", "some", "any", "each", "every",
    "all", "both", "many", "most", "such", "other", "another", "one",
})

# If any of these appear anywhere in the phrase it is a clause, not an
# entity. This is the rule that kills "symbol that represents".
_CLAUSE_MARKERS = frozenset({
    "that", "which", "who", "whom", "whose", "where", "when", "while",
    "is", "are", "was", "were", "be", "been", "being", "am",
    "has", "have", "had", "do", "does", "did",
    "will", "would", "can", "could", "may", "might", "should", "must",
    "and", "or", "but", "if", "because", "although", "however", "than",
    "not", "there", "then", "thus", "therefore",
})

# A phrase may not END with one of these — it is dangling.
# This is the rule that kills "responsible for" and "used to".
_TRAILING_DROP = frozenset({
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "into",
    "about", "over", "under", "through", "during", "between", "among",
    "as", "without", "within", "across", "upon", "near", "per", "onto",
    "against", "toward", "towards", "after", "before", "via", "off", "out",
    "up", "down", "like", "such", "very", "more", "less",
})

# Finite verb forms / participles that mark a verb phrase rather than a
# concept. Checked on EVERY token, because the verb can head the phrase
# ("using smell") as easily as tail it ("commonly used"). -ing
# nominalisations ("overgrazing", "warming", "flooding") are deliberately
# NOT rejected — they are legitimate concepts and central to real causal
# chains — except for the transitive verbs listed here, which never head a
# noun phrase. This is the rule that kills "using smell" and "represents".
_VERB_TAIL = frozenset({
    "using", "being", "having", "doing", "making", "getting", "taking",
    "giving", "showing", "representing", "including", "containing",
    "causing", "creating", "producing", "providing", "allowing",
    "requiring", "affecting", "involving", "leading", "resulting",
    "represents", "means", "refers", "called", "known", "found", "made",
    "based", "regarded", "considered", "referred", "defined", "described",
    "said", "used", "given", "seen", "taken", "become", "becomes",
    "includes", "consists", "occurs", "happens", "appears", "seems",
})

# Predicate adjectives. These survive the trailing-preposition strip
# ("responsible for" → "responsible") but are still not names of anything,
# so they are rejected explicitly rather than repaired into a pseudo-concept.
_ADJ_HEADS = frozenset({
    "responsible", "dependent", "capable", "similar", "due", "prone",
    "subject", "part", "full", "aware", "typical", "characteristic",
    "able", "unable", "likely", "unlikely", "common", "important",
})

# Words ending in "-ed" that really are nouns/adjectives, exempted from the
# participle rule below.
_ED_ALLOW = frozenset({
    "seed", "seaweed", "feed", "weed", "speed", "breed", "greed", "shed",
    "bed", "need", "reed", "deed", "creed", "tweed", "hundred", "sacred",
    "thread", "spread", "bread", "dead", "head", "lead", "read", "red",
    "wed", "fed", "bled", "sled", "shred",
})


def canonicalize_entity(raw: Any) -> str:
    """
    Reduce a model-emitted entity string to a canonical concept name,
    or return "" if it is not an entity at all.

    Canonical form: lowercase, ≤ MAX_ENTITY_WORDS words, no leading article,
    no possessive, no trailing preposition, no clause, no verb tail.

    Two kinds of edit, kept deliberately distinct:
      REPAIR  — leading determiners, possessives and dangling function words
                are stripped, because the underlying name is unambiguous:
                "the deer populations in" → "deer populations".
      REJECT  — anything whose head is not a noun is dropped whole:
                "using smell", "symbol that represents", "responsible for".

    Returning "" is the common, correct outcome for a fragment. Callers
    drop the whole triple — a half-referential edge is worse than no edge.
    """
    if not isinstance(raw, str):
        return ""

    text = raw.strip().lower()
    if not text:
        return ""

    # Strip possessives before punctuation removal ("wolf's" → "wolf").
    text = re.sub(r"'s\b", "", text)
    # Keep letters, digits, spaces and internal hyphens; drop everything else.
    text = re.sub(r"[^a-z0-9\- ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    words = text.split()

    # Strip leading determiners (possibly stacked: "all the wolves").
    while words and words[0] in _LEADING_DROP:
        words = words[1:]
    # Strip dangling trailing function words before judging length.
    while words and words[-1] in _TRAILING_DROP:
        words = words[:-1]
    if not words:
        return ""

    # ── Rejection rules ───────────────────────────────────────────────
    if len(words) > MAX_ENTITY_WORDS:
        return ""                                   # a clause, not a name
    if any(w in _CLAUSE_MARKERS for w in words):
        return ""                                   # crosses a clause boundary
    if any(w in _VERB_TAIL for w in words):
        return ""                                   # verb phrase, either end
    last = words[-1]
    if last in _ADJ_HEADS:
        return ""                                   # predicate adjective
    if last.endswith("ed") and len(last) >= 5 and last not in _ED_ALLOW:
        return ""                                   # participle tail
    if not any(c.isalpha() for c in "".join(words)):
        return ""                                   # pure numerals / junk

    result = " ".join(words).strip("- ")
    if len(result) < 2:
        return ""
    return result


def is_fragment(text: str) -> bool:
    """
    True when `text` would be rejected as a non-referential fragment.

    Exposed so evaluation harnesses can score BOTH arms with one judge.
    Note the asymmetry this creates: Arm B filters on exactly this
    predicate, so its fragment rate is 0 by construction. Read the metric
    as "what the extractor emits", not as an independent verdict.
    """
    return canonicalize_entity(text) == ""


# ==================================================================
# Prompt + response schema
# ==================================================================

_SYSTEM_PROMPT = """\
You extract a knowledge graph from text. You output JSON only.

Each triple is (subject, relation, object).

SUBJECT and OBJECT rules — these are strict, violations are discarded:
- Must be a SHORT NOUN PHRASE naming an entity or a concept.
- Maximum 4 words. Prefer 1-2.
- Lowercase. No articles ("the", "a", "an"). No possessives.
- Never a clause, a verb phrase, or a sentence fragment.
- Never end with a preposition or a verb.
- Use the same canonical name every time the same thing is mentioned, so
  that triples from different sentences connect. Prefer the plain plural or
  mass-noun form ("wolves", "soil erosion"), not the sentence's wording.

  GOOD: "wolves", "soil erosion", "atmospheric carbon dioxide", "roman republic"
  BAD:  "using smell", "symbol that represents", "responsible for",
        "wolves that were reintroduced", "it", "they", "this process"

RELATION must be exactly one of:
  CAUSES    X produces Y as a consequence
  CONTROLS  X regulates or governs the level of Y
  PREVENTS  X stops Y from occurring
  ENABLES   X makes Y possible
  REQUIRES  X depends on Y; Y is necessary for X
  IS_A      X is a type, instance or part of Y
  PREDATES  X eats, hunts or preys on Y
  AFFECTS   X has some effect on Y, direction unspecified
  CONTAINS  X is composed of or includes Y
Never output any other relation name.

CONFIDENCE is your own 0.0-1.0 estimate that the text asserts this triple.

Extract only what the text states or directly implies. Do not add world
knowledge. Prefer fewer, cleaner triples over many noisy ones. If the text
states nothing relational, return an empty list."""

_USER_TEMPLATE = """\
Extract the knowledge-graph triples from the following text.

TEXT:
\"\"\"
{text}
\"\"\"

Return JSON: {{"triples": [{{"subject": ..., "relation": ..., "object": ..., "confidence": ...}}]}}"""

# Optional cross-document entity linking. Canonicalisation normalises FORM
# ("The Wolves." → "wolves"); it cannot normalise REFERENCE ("gray wolf" and
# "wolves" stay two nodes). Bridge nodes need the same string to recur across
# documents, so the glossary shows the model the names already in the graph.
# Off by default — it makes the extractor stateful, which is a change to the
# experiment, not just to the component. Turn it on deliberately, as its own
# arm, to measure how much of the bridge-node count is entity linking.
_GLOSSARY_BLOCK = """

Names already used in this knowledge graph. If the text refers to one of
these, reuse the exact string so the graph connects:
{names}"""

# llama.cpp accepts this under response_format for constrained decoding; it
# converts the schema to a GBNF grammar internally.
_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "triples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject":    {"type": "string", "maxLength": 60},
                    "relation":   {"type": "string", "enum": sorted(RELATION_TYPES)},
                    "object":     {"type": "string", "maxLength": 60},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["subject", "relation", "object", "confidence"],
            },
            "maxItems": 20,
        }
    },
    "required": ["triples"],
}


def _normalise_endpoint(url: str) -> str:
    """Accept a base URL, a /v1 URL, or a full chat-completions URL."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return _DEFAULT_URL
    if u.endswith("/chat/completions"):
        return u
    if u.endswith("/v1"):
        return u + "/chat/completions"
    return u + "/v1/chat/completions"


# ==================================================================
# Processor
# ==================================================================

class LLMTextProcessor(BaseProcessor):
    """
    Drop-in LLM replacement for TextProcessor's relation extraction.

        brain = Orchestrator(db_path=...)
        brain.processors["text"] = LLMTextProcessor()

    Nothing else in v1 changes.

    Parameters
    ----------
    url, model, timeout
        Override the environment configuration.
    offline
        Force dry-run mode: no HTTP, zero relations, valid output.
    brain
        Optional Orchestrator. When supplied, failures are routed to
        `brain.survival.resilience.error_log` per v1 convention.
    transport
        Optional callable(system_prompt, user_prompt) -> str returning the
        raw model message content. Used by tests to exercise parsing and
        canonicalisation without a server.
    glossary
        When True, names already extracted are shown to the model on later
        documents so the same concept keeps the same string. Off by default:
        it makes the extractor stateful and should be measured as its own
        arm, not folded silently into the LLM arm.
    """

    name = "text"   # must match TextProcessor for drop-in dispatch

    def __init__(
        self,
        url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        offline: bool = False,
        brain: Any = None,
        transport: Optional[Callable[[str, str], str]] = None,
        glossary: bool = False,
    ):
        self._url   = _normalise_endpoint(url or os.environ.get("GENESIS_LLM_URL", _DEFAULT_URL))
        self._model = model or os.environ.get("GENESIS_LLM_MODEL", _DEFAULT_MODEL)
        try:
            self._timeout = float(timeout if timeout is not None
                                  else os.environ.get("GENESIS_LLM_TIMEOUT", _DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            self._timeout = _DEFAULT_TIMEOUT

        env_offline = os.environ.get("GENESIS_LLM_OFFLINE", "").strip() in {"1", "true", "yes"}
        self.offline = bool(offline or env_offline)
        self._brain = brain
        self._transport = transport

        # Cross-document entity linking (opt-in). name → times emitted.
        self.use_glossary = bool(glossary)
        self._glossary: dict[str, int] = {}
        self.glossary_size = 30

        # Set once the server has proven unreachable, so a 30-document run
        # doesn't pay the timeout 30 times.
        self._unreachable = False

        # Diagnostics — read by the falsification harness.
        self.calls = 0
        self.failures = 0
        self.triples_seen = 0
        self.triples_kept = 0
        self.rejected_entity = 0
        self.rejected_relation = 0
        self.truncated_outputs = 0
        self.last_error: str = ""

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """
        True when a llama-server is answering at the configured endpoint.

        Cheap GET against /v1/models. Never raises.
        """
        if self.offline:
            return False
        if self._transport is not None:
            return True
        try:
            import requests
        except ImportError:
            return False
        models_url = self._url.replace("/chat/completions", "/models")
        try:
            resp = requests.get(models_url, timeout=3)
            return resp.status_code < 500
        except Exception as exc:
            self._log("llm_text.probe", exc)
            return False

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _process(self, data: Any) -> ProcessorOutput:
        text = str(data)
        sentences = _split_sentences(text)

        # ── Surface features: identical helpers to TextProcessor, so the
        #    only measurable difference between the arms is relations. ──
        all_words = re.findall(r"\b\w+\b", text.lower())
        word_set = set(all_words)
        keywords = sorted(
            {w for w in word_set if w not in _STOPWORDS and len(w) >= 3},
            key=len, reverse=True
        )[:12]
        categories = [c for c, cw in _CATEGORIES.items() if word_set & cw]

        pos_count = len(word_set & _POSITIVE)
        neg_count = len(word_set & _NEGATIVE)
        sentiment = ("positive" if pos_count > neg_count else
                     "negative" if neg_count > pos_count else "neutral")

        entities   = _extract_entities(text, sentences)
        claim_type = _classify_claim(text, word_set)

        # ── Relations: LLM only. No regex fallback, ever. A fallback would
        #    contaminate the falsification test with the thing under test. ──
        relations: list[dict] = []
        error: str = ""
        degraded = False

        prompt_text, truncated_chars = _truncate(text, MAX_INPUT_CHARS)

        if not prompt_text.strip():
            degraded = False           # empty input is not a failure
        elif self.offline or self._unreachable:
            degraded = True
            error = "offline" if self.offline else f"unreachable: {self.last_error}"
        else:
            raw, error = self._call_llm(prompt_text)
            if raw is None:
                degraded = True
            else:
                relations = self._parse_triples(raw)

        truncated_relations = max(0, len(relations) - MAX_RELATIONS)
        if truncated_relations:
            self.truncated_outputs += 1
        relations = relations[:MAX_RELATIONS]

        causal_markers = sorted({r["relation"] for r in relations})

        # ── Importance / confidence: same formulas as TextProcessor ──────
        importance = min(1.0,
            len(keywords) * 0.04
            + len(relations) * 0.18
            + len(entities) * 0.04
            + (0.08 if sentiment != "neutral" else 0.0)
            + (0.05 if claim_type != "fact" else 0.0)
        )
        importance = max(0.15, importance)

        if entities:
            raw_key = "_".join(e.lower().replace(" ", "_") for e in entities[:2])
        elif relations:
            raw_key = f"{relations[0]['subject']}_{relations[0]['object']}"[:30]
        elif categories:
            raw_key = "_".join(categories[:2])
        else:
            raw_key = "_".join(keywords[:2]) if keywords else str(abs(hash(text)) % 9999)
        suggested_key = f"text:{re.sub(r'[^a-z0-9_]', '', raw_key)[:40]}"

        confidence = 0.5
        if relations:
            confidence = max(confidence, max(r["confidence"] for r in relations))
        if entities:
            confidence = min(1.0, confidence + 0.1)
        if degraded:
            confidence = min(confidence, 0.3)

        extracted = {
            "keywords":       keywords[:10],
            "categories":     categories,
            "sentiment":      sentiment,
            "word_count":     len(all_words),
            "entities":       entities,
            "claim_type":     claim_type,
            "relations":      relations,
            "causal_markers": causal_markers,
            # ── extractor diagnostics (additive; nothing downstream reads these)
            "extractor":            "llm",
            "llm_available":        not degraded,
            "llm_model":            self._model,
            "llm_truncated_chars":  truncated_chars,
            "llm_dropped_relations": truncated_relations,
        }
        if error:
            extracted["error"] = error

        return ProcessorOutput(
            source=self.name,
            input_data=text,
            extracted=extracted,
            importance=importance,
            suggested_key=suggested_key,
            context=_build_context(categories, sentiment, entities, relations, claim_type),
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Model call
    # ------------------------------------------------------------------

    def _call_llm(self, text: str) -> tuple[Optional[str], str]:
        """
        Return (raw_message_content, error_string).

        On any failure returns (None, reason). Never raises. A connection
        failure latches `self._unreachable` so the rest of a corpus run
        degrades immediately instead of timing out per document.
        """
        self.calls += 1
        user_prompt = _USER_TEMPLATE.format(text=text) + self._glossary_block()

        if self._transport is not None:
            try:
                return self._transport(_SYSTEM_PROMPT, user_prompt), ""
            except Exception as exc:
                self.failures += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                self._log("llm_text.transport", exc)
                return None, self.last_error

        try:
            import requests
        except ImportError as exc:
            self.failures += 1
            self._unreachable = True
            self.last_error = "requests not installed"
            self._log("llm_text.import", exc)
            return None, self.last_error

        payload = {
            "model":       self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": 0.0,        # extraction, not generation
            "max_tokens":  1024,
            "stream":      False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "triples", "strict": True,
                                "schema": _JSON_SCHEMA},
            },
        }

        for attempt in (0, 1):
            try:
                resp = requests.post(self._url, json=payload, timeout=self._timeout)
            except Exception as exc:
                # Connection-level failure — the server is not there.
                self.failures += 1
                self._unreachable = True
                self.last_error = f"{type(exc).__name__}: {exc}"
                self._log("llm_text.connect", exc)
                return None, self.last_error

            if resp.status_code >= 400:
                # A build that rejects json_schema still honours json_object;
                # retry once in the looser mode before giving up.
                if attempt == 0 and resp.status_code < 500:
                    payload["response_format"] = {"type": "json_object"}
                    continue
                self.failures += 1
                self.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                self._log("llm_text.http", RuntimeError(self.last_error))
                return None, self.last_error

            try:
                content = resp.json()["choices"][0]["message"]["content"]
            except Exception as exc:
                self.failures += 1
                self.last_error = f"malformed response: {type(exc).__name__}: {exc}"
                self._log("llm_text.decode", exc)
                return None, self.last_error

            return (content or ""), ""

        return None, self.last_error or "unknown failure"

    # ------------------------------------------------------------------
    # Parsing + canonicalisation
    # ------------------------------------------------------------------

    def _parse_triples(self, raw: str) -> list[dict]:
        """
        Turn a raw model message into canonical v1 triples.

        Everything that does not survive canonicalisation is dropped and
        counted. Never raises.
        """
        payload = _load_json(raw)
        if payload is None:
            self.failures += 1
            self.last_error = "unparseable JSON from model"
            self._log("llm_text.json", ValueError(self.last_error))
            return []

        if isinstance(payload, dict):
            items = payload.get("triples")
            if items is None:
                # Tolerate {"relations": [...]} or a bare single triple.
                items = payload.get("relations")
            if items is None and {"subject", "object"} <= set(payload):
                items = [payload]
        else:
            items = payload
        if not isinstance(items, list):
            return []

        seen: set[tuple[str, str, str]] = set()
        out: list[dict] = []
        for item in items:
            self.triples_seen += 1
            if not isinstance(item, dict):
                self.rejected_relation += 1
                continue

            rel = map_relation(item.get("relation") or item.get("predicate"))
            if rel is None:
                self.rejected_relation += 1
                continue

            subject = canonicalize_entity(item.get("subject"))
            obj     = canonicalize_entity(item.get("object"))
            if not subject or not obj or subject == obj:
                self.rejected_entity += 1
                continue

            key = (subject, rel, obj)
            if key in seen:
                continue
            seen.add(key)

            out.append({
                "subject":    subject,
                "relation":   rel,
                "object":     obj,
                "confidence": _clamp_confidence(item.get("confidence")),
            })
            self.triples_kept += 1
            self._remember(subject)
            self._remember(obj)

        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _glossary_block(self) -> str:
        """The known-names hint appended to the user prompt, or ""."""
        if not self.use_glossary or not self._glossary:
            return ""
        names = sorted(self._glossary, key=lambda n: (-self._glossary[n], n))
        return _GLOSSARY_BLOCK.format(
            names=", ".join(names[:self.glossary_size])
        )

    def _remember(self, name: str) -> None:
        if self.use_glossary and name:
            self._glossary[name] = self._glossary.get(name, 0) + 1

    def _log(self, label: str, exc: Exception) -> None:
        """Route to the survival error log when a brain is in scope."""
        brain = self._brain
        if brain is None:
            return
        try:
            brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            # The error log itself is unavailable; the failure is already
            # carried in self.last_error and in extracted["error"].
            pass

    def diagnostics(self) -> dict:
        """Counters for the falsification harness."""
        return {
            "calls":              self.calls,
            "failures":           self.failures,
            "triples_seen":       self.triples_seen,
            "triples_kept":       self.triples_kept,
            "rejected_entity":    self.rejected_entity,
            "rejected_relation":  self.rejected_relation,
            "truncated_outputs":  self.truncated_outputs,
            "glossary":           self.use_glossary,
            "glossary_names":     len(self._glossary),
            "unreachable":        self._unreachable,
            "offline":            self.offline,
            "last_error":         self.last_error,
        }


# ==================================================================
# Helpers
# ==================================================================

def _clamp_confidence(value: Any) -> float:
    """Model confidence → a sane float in [_CONF_FLOOR, _CONF_CEIL]."""
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return _CONF_DEFAULT
    if conf != conf:                      # NaN
        return _CONF_DEFAULT
    if conf > 1.0:                        # a model that answered in percent
        conf = conf / 100.0 if conf <= 100.0 else 1.0
    return max(_CONF_FLOOR, min(_CONF_CEIL, conf))


def _truncate(text: str, limit: int) -> tuple[str, int]:
    """Truncate at a sentence boundary. Returns (text, chars_dropped)."""
    if len(text) <= limit:
        return text, 0
    head = text[:limit]
    cut = max(head.rfind(". "), head.rfind("\n"))
    if cut > limit // 2:
        head = head[:cut + 1]
    return head, len(text) - len(head)


def _load_json(raw: str) -> Any:
    """
    Parse JSON from a model message, tolerating fenced or prefixed output.
    Returns None when nothing parseable is present.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    # Strip ``` fences
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except Exception:
            pass
    # First balanced {...} or [...] span
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if 0 <= start < end:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                continue
    return None
