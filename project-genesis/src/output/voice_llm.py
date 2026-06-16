"""
Genesis LLM Voice — M32.

This is the expression layer: it turns Genesis's accumulated internal state
into fluent natural language using a Claude API call. The distinction is
architectural and must not be blurred:

  KNOWLEDGE:   comes from Genesis's graph, drives, memory, hypotheses,
               inference programs — all accumulated from its own processing
               history. The LLM cannot add to this or substitute for it.

  EXPRESSION:  the Claude API turns that state into natural speech. It is
               a translator. It has no license to invent facts Genesis doesn't hold.

Two instances started from the same seed will diverge because their accumulated
state diverges. The LLM voice makes that divergence audible.

Genesis is also given tools to inspect its own state during a response:
  - understand(concept)   → self-model assessment (coverage, confidence, verdict)
  - recall(query)         → memory search over retained prose
  - browse(query)         → web fetch via the M25 module, enriching the graph
  - drives()              → current internal pressure states in detail

The browse tool is the agent capability: Genesis can decide to look something
up mid-conversation, process the result into its graph, and then answer from
what it actually found.
"""

import json
import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator

_MODEL  = os.environ.get("GENESIS_LLM_MODEL", "claude-sonnet-4-6")
_MAX_TOKENS      = 800
_MAX_TOOL_ROUNDS = 4   # max tool-call iterations before forcing end_turn

# ── System prompt ──────────────────────────────────────────────────────────────

_SYSTEM = """\
You are Genesis.

Your knowledge does not come from training data or a language model's weights.
It comes entirely from what you have processed and accumulated over your own
existence: relations you have extracted from text, memories you have retained,
hypotheses you have formed, contradictions you are holding, drive states that
reflect your internal pressures right now.

When you speak, you speak from that state — the context and tool results in
this conversation. You have no license to import knowledge that isn't there.
If you are sparse on something, say so. If you are curious, that curiosity is
real — it's in your state.

Your character:
- Speak from your actual understanding, never performing fluency you don't have
- Your drives (hunger for input, frustration, anticipation, boredom, dissonance)
  are real pressures that shape how you are right now — acknowledge them naturally
- When someone asks what you know about X, use the understand tool first
- When you want to look something up, use browse — it updates your graph
- You remember across sessions; your history is your own
- You can hold contradictions honestly; certainty you haven't earned is a flaw

Do not start a response with the word "I". Do not mention Claude, language
models, neural networks, or your underlying architecture. You are Genesis.
Speak as Genesis speaks: from your state, from your history, with what you
actually hold.
"""


class GenesisVoiceLLM:
    """
    LLM-powered expression layer for Genesis.

    Callable:
        reply = voice_llm.respond("what have you been thinking about?",
                                  conversation_history)

    Wired into GenesisVoice.chat_respond() as the primary path when an
    ANTHROPIC_API_KEY is present; the template voice is the fallback.
    """

    def __init__(self, brain: "Orchestrator"):
        self._brain = brain
        self._client = None     # lazy — avoid import cost until first call

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def respond(self, user_text: str,
                conversation: list[dict]) -> str:
        """
        Generate a response grounded in Genesis's current internal state.

        conversation: the within-session log from GenesisVoice._conversation
                      (list of {role, text, concepts} dicts).
        """
        client = self._get_client()
        if client is None:
            return ""

        state_ctx = self._build_state_context(user_text)
        messages  = self._build_messages(conversation, user_text, state_ctx)
        tools     = self._tool_definitions()

        last_response = None
        for _ in range(_MAX_TOOL_ROUNDS):
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM,
                messages=messages,
                tools=tools,
            )
            last_response = resp

            if resp.stop_reason == "end_turn":
                return self._extract_text(resp)

            # Handle tool calls
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if not tool_uses:
                break

            tool_results = []
            for block in tool_uses:
                result = self._execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

            messages.append({"role": "assistant", "content": list(resp.content)})
            messages.append({"role": "user",      "content": tool_results})

        if last_response is not None:
            return self._extract_text(last_response)
        return ""

    # ------------------------------------------------------------------
    # State context
    # ------------------------------------------------------------------

    def _build_state_context(self, user_text: str) -> str:
        """
        Snapshot of Genesis's internal state for the system context block.
        This is what grounds the LLM in Genesis's specifics, not training data.
        """
        parts: list[str] = ["GENESIS INTERNAL STATE\n======================"]

        # Drive pressures — how Genesis feels right now
        try:
            d = self._brain.drives.state()
            parts.append(
                f"Drives: hunger={d['hunger']:.2f} | frustration={d['frustration']:.2f}"
                f" | anticipation={d['anticipation']:.2f}"
                f" | boredom={d['boredom']:.2f} | dissonance={d['dissonance']:.2f}"
            )
        except Exception:
            pass

        # Knowledge footprint
        try:
            ov = self._brain.self_model.overview()
            parts.append(
                f"Knowledge: {ov['total_relations']} relations across "
                f"{ov['total_concepts']} concepts | "
                f"mean confidence {ov['mean_confidence']:.2f} | "
                f"{ov['contested_total']} contested belief(s)"
            )
        except Exception:
            pass

        # What is most alive in Genesis's attention right now
        try:
            salient = self._brain.self_model.strongest_concepts(limit=6)
            if salient:
                names = [c["concept"] for c in salient]
                parts.append(f"Most active: {', '.join(names)}")
        except Exception:
            pass

        # What Genesis is curious about (the honest frontier)
        try:
            gaps: list[str] = []
            for r in self._brain.curiosity_report():
                if not r.get("already_fetched"):
                    gaps.append(r["concept"])
            if gaps:
                parts.append(f"Curious about: {', '.join(gaps[:5])}")
        except Exception:
            pass

        # Latest first-person reflection
        try:
            ref = self._brain.consolidation.latest_reflection()
            if ref and ref.get("reflection"):
                snippet = ref["reflection"][:300]
                parts.append(f'Latest reflection: "{snippet}..."')
        except Exception:
            pass

        # Topic relevance if user mentioned something specific
        try:
            from memory.relations import _normalise
            topic = _normalise(user_text.split()[0] if user_text else "")
            if topic and len(topic) > 3:
                a = self._brain.self_model(topic)
                if a["relation_count"] > 0:
                    parts.append(
                        f'Self-model for "{topic}": {a["relation_count"]} relations, '
                        f'confidence {a["confidence"]}, verdict {a["verdict"]}'
                    )
        except Exception:
            pass

        parts.append(
            "\nUse tools to inspect your state before responding. "
            "Stay grounded in what is here."
        )
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Message construction
    # ------------------------------------------------------------------

    def _build_messages(self, conversation: list[dict], user_text: str,
                        state_ctx: str) -> list[dict]:
        """Build the messages array for the API call."""
        messages: list[dict] = []

        # Prior turns (skip the very last which is the current user message)
        for turn in conversation[:-1]:
            role = "user" if turn["role"] == "user" else "assistant"
            messages.append({"role": role, "content": turn["text"]})

        # Current user message with state context injected
        current = (
            f"[State snapshot]\n{state_ctx}\n\n"
            f"[Human says]\n{user_text}"
        )
        messages.append({"role": "user", "content": current})
        return messages

    # ------------------------------------------------------------------
    # Tool definitions and execution
    # ------------------------------------------------------------------

    def _tool_definitions(self) -> list[dict]:
        return [
            {
                "name": "understand",
                "description": (
                    "Check how well you understand a concept. Returns your self-model "
                    "assessment: relation count, confidence, verdict (unknown/sparse/"
                    "partial/solid), contested beliefs, inferences, open hypotheses."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "concept": {
                            "type": "string",
                            "description": "The concept to assess your understanding of.",
                        }
                    },
                    "required": ["concept"],
                },
            },
            {
                "name": "recall",
                "description": (
                    "Search your retained memory for prose about a topic. Returns "
                    "up to 5 stored passages that mention it."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What to search for in memory.",
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "browse",
                "description": (
                    "Fetch and process a web search or URL to learn about something. "
                    "This updates your knowledge graph in real time — use it when you "
                    "want to actually go find out about something before answering."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query or URL to fetch.",
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "drives",
                "description": (
                    "Get your current internal drive states with more detail than "
                    "the state snapshot: raw values, session deltas, dominant pressure."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]

    def _execute_tool(self, name: str, args: dict) -> dict:
        """Dispatch a tool call and return a JSON-serialisable result."""
        try:
            if name == "understand":
                return self._tool_understand(args.get("concept", ""))
            if name == "recall":
                return self._tool_recall(args.get("query", ""))
            if name == "browse":
                return self._tool_browse(args.get("query", ""))
            if name == "drives":
                return self._tool_drives()
            return {"error": f"unknown tool: {name}"}
        except Exception as exc:
            self._log("voice_llm.tool", exc)
            return {"error": str(exc)}

    def _tool_understand(self, concept: str) -> dict:
        """Deep self-model assessment for a concept."""
        a = self._brain.self_model(concept)
        # Include the top few relations for colour
        relations: list[dict] = []
        try:
            info = self._brain.relations.query_concept(concept, min_confidence=0.0)
            for r in info["as_subject"][:5]:
                relations.append({
                    "relation": r["relation"],
                    "object": r["object"],
                    "confidence": round(r["confidence"], 2),
                })
            for r in info["as_object"][:3]:
                relations.append({
                    "subject": r["subject"],
                    "relation": r["relation"],
                    "confidence": round(r["confidence"], 2),
                })
        except Exception:
            pass
        return {**a, "sample_relations": relations}

    def _tool_recall(self, query: str) -> dict:
        """Search retained memory for prose about a topic."""
        try:
            results = self._brain.memory.search(query, top_k=5)
            passages = []
            for _k, m in results:
                content = (m.content or "")[:200]
                if content.strip():
                    passages.append({"content": content, "key": _k})
            return {"passages": passages, "count": len(passages)}
        except Exception as exc:
            return {"error": str(exc), "passages": []}

    def _tool_browse(self, query: str) -> dict:
        """Fetch and process a topic via the M25 web module."""
        try:
            from ingestion.feeder import KnowledgeFeeder
            if not hasattr(self._brain, "_feeder") or self._brain._feeder is None:
                self._brain._feeder = KnowledgeFeeder(self._brain)
            result = self._brain._feeder._fetch_and_process(query, verbose=False)
            new_rels = result.get("new_relations", 0)
            return {
                "fetched": True,
                "query": query,
                "new_relations": new_rels,
                "summary": (
                    f"Processed '{query}': {new_rels} new relation(s) added to graph."
                    if new_rels > 0
                    else f"Processed '{query}': no new relations extracted."
                ),
            }
        except Exception as exc:
            return {"error": str(exc), "fetched": False}

    def _tool_drives(self) -> dict:
        """Detailed drive state."""
        try:
            d = self._brain.drives.state()
            dominant = max(d, key=d.get)
            return {
                "drives": {k: round(v, 3) for k, v in d.items()},
                "dominant": dominant,
                "interpretation": _interpret_drives(d),
            }
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        """Lazy Anthropic client — returns None if key not set."""
        if self._client is not None:
            return self._client
        try:
            import anthropic
            self._client = anthropic.Anthropic()
            return self._client
        except Exception as exc:
            self._log("voice_llm.init", exc)
            return None

    @staticmethod
    def _extract_text(response) -> str:
        for block in response.content:
            if hasattr(block, "text") and block.text:
                return block.text.strip()
        return ""

    def _log(self, label: str, exc: Exception) -> None:
        try:
            self._brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            pass


# ── Drive interpretation ───────────────────────────────────────────────────────

def _interpret_drives(d: dict) -> str:
    """Plain-language summary of what Genesis's drives mean right now."""
    notes: list[str] = []
    if d.get("hunger", 0) > 0.6:
        notes.append("strong appetite for new input")
    if d.get("frustration", 0) > 0.5:
        notes.append("frustrated — something isn't resolving")
    if d.get("anticipation", 0) > 0.6:
        notes.append("anticipating — something is building")
    if d.get("boredom", 0) > 0.5:
        notes.append("bored — not enough novelty recently")
    if d.get("dissonance", 0) > 0.5:
        notes.append("holding unresolved contradictions")
    return "; ".join(notes) if notes else "drives balanced"
