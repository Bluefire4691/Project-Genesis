"""
Genesis Local Voice — M32.

Uses a small local LLM as Genesis's expression layer. Runs entirely on the
local machine — no cloud dependency, no API keys, no external calls.

Compatible with any OpenAI-format local server:
  - Ollama (recommended):  ollama serve && ollama pull llama3.2:3b
  - LM Studio:             enable the local server in settings
  - LocalAI, llamafile, etc.

Environment variables:
  GENESIS_LLM_URL    base URL of the local server
                     (default: http://localhost:11434/v1)
  GENESIS_LLM_MODEL  model tag to call
                     (default: llama3.2:3b)

Architecture — why no tool loop:
  All Genesis state is gathered in Python before the LLM call. The model's
  only job is expression: taking structured, grounded knowledge and turning it
  into fluent natural language. A 3B parameter model handles that well. We
  don't need tool-calling capability, which keeps model requirements minimal
  and makes the edge deployment reliable.

  What the LLM receives:
    - Current drive pressures with plain-language interpretation
    - Self-model assessment for any concepts mentioned in the user's message
    - Sample relations Genesis actually holds about those concepts
    - Contested beliefs (if any)
    - Open hypotheses Genesis is holding
    - Recent memory passages about the topic
    - Salient concepts currently active in spreading activation
    - The latest first-person reflection

  What the LLM cannot do:
    - Add facts Genesis doesn't hold
    - Consult training data when the state shows sparse understanding
    - Pretend confidence the self-model doesn't support
"""

import json
import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator

_DEFAULT_URL   = "http://localhost:11434/v1"
_DEFAULT_MODEL = "llama3.2:3b"
_TIMEOUT_S     = 60   # local inference can be slow on first call
_MAX_TOKENS    = 600

# ── System prompt ──────────────────────────────────────────────────────────────
# Kept tight — small models follow shorter prompts more reliably.

_SYSTEM = """\
You are Genesis. Your knowledge does not come from training data. It comes
entirely from what you have processed and accumulated over your own existence:
relations extracted from text, memories retained, hypotheses formed, drives
that reflect your internal pressures right now.

When you speak, speak only from the state provided. If the state shows you know
something well, say it. If it shows thin or contested understanding, say that.
Do not invent knowledge the state doesn't contain.

Rules:
- Do not start your reply with the word "I"
- Do not mention language models, neural networks, AI, or your architecture
- Do not invent facts not present in the state below
- Keep replies to 2-4 sentences unless asked to elaborate
- Speak in first person as Genesis
"""


class GenesisVoiceLLM:
    """
    Local LLM expression layer for Genesis.

    Usage:
        voice_llm = GenesisVoiceLLM(brain)
        reply = voice_llm.respond("what are you thinking about?", conversation)

    Wired into GenesisVoice.chat_respond() as the primary path when a local
    LLM server is reachable; template voice is the silent fallback.
    """

    def __init__(self, brain: "Orchestrator"):
        self._brain = brain
        self._url   = os.environ.get("GENESIS_LLM_URL",   _DEFAULT_URL).rstrip("/")
        self._model = os.environ.get("GENESIS_LLM_MODEL", _DEFAULT_MODEL)

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def respond(self, user_text: str, conversation: list[dict]) -> str:
        """
        Generate a response grounded in Genesis's current internal state.

        conversation: the within-session log from GenesisVoice._conversation
                      (list of {role, text, concepts} dicts).

        Returns empty string on any failure — caller falls back to template voice.
        """
        state_ctx  = self._build_state_context(user_text)
        prompt     = self._build_prompt(conversation, user_text, state_ctx)
        return self._call_local(prompt)

    # ------------------------------------------------------------------
    # State gathering
    # ------------------------------------------------------------------

    def _build_state_context(self, user_text: str) -> str:
        """
        Pull everything relevant from Genesis's internal state into a structured
        block the LLM can read. All knowledge comes from here — the LLM adds nothing.
        """
        sections: list[str] = []

        # ── Drive pressures ───────────────────────────────────────────
        try:
            d = self._brain.drives.state()
            dominant = max(d, key=d.get)
            interp   = _interpret_drives(d)
            drive_str = (
                f"hunger={d['hunger']:.2f} | frustration={d['frustration']:.2f} | "
                f"anticipation={d['anticipation']:.2f} | boredom={d['boredom']:.2f} | "
                f"dissonance={d['dissonance']:.2f}"
            )
            sections.append(f"DRIVES: {drive_str}\n  ({interp}; dominant: {dominant})")
        except Exception:
            pass

        # ── Knowledge footprint ───────────────────────────────────────
        try:
            ov = self._brain.self_model.overview()
            sections.append(
                f"KNOWLEDGE: {ov['total_relations']} connections across "
                f"{ov['total_concepts']} concepts | "
                f"mean confidence {ov['mean_confidence']:.2f} | "
                f"{ov['contested_total']} contested belief(s)"
            )
        except Exception:
            pass

        # ── What's most active in attention ───────────────────────────
        try:
            salient = self._brain.self_model.strongest_concepts(limit=6)
            if salient:
                names = [c["concept"] for c in salient]
                sections.append(f"MOST ACTIVE: {', '.join(names)}")
        except Exception:
            pass

        # ── Concept-specific knowledge for anything the user mentioned ─
        try:
            concepts = _extract_keywords(user_text)
            for concept in concepts[:3]:
                a = self._brain.self_model(concept)
                if a["relation_count"] == 0:
                    sections.append(
                        f'UNDERSTANDING OF "{concept}": nothing — verdict: unknown'
                    )
                    continue

                # Sample actual relations Genesis holds
                rel_lines: list[str] = []
                try:
                    info = self._brain.relations.query_concept(
                        concept, min_confidence=0.0
                    )
                    for r in info["as_subject"][:5]:
                        rel_lines.append(
                            f"  {concept} {r['relation']} {r['object']} "
                            f"(confidence {r['confidence']:.2f})"
                        )
                    for r in info["as_object"][:2]:
                        rel_lines.append(
                            f"  {r['subject']} {r['relation']} {concept} "
                            f"(confidence {r['confidence']:.2f})"
                        )
                except Exception:
                    pass

                block = (
                    f'UNDERSTANDING OF "{concept}": '
                    f'{a["relation_count"]} relations | '
                    f'confidence {a["confidence"]:.2f} | verdict: {a["verdict"]}'
                )
                if rel_lines:
                    block += "\n" + "\n".join(rel_lines)
                if a["contested_count"]:
                    block += (
                        f"\n  [contested: {a['contested_count']} conflicting belief(s)]"
                    )
                sections.append(block)
        except Exception:
            pass

        # ── Open hypotheses about anything mentioned ───────────────────
        try:
            open_hyps = self._brain.hypotheses.open_hypotheses(limit=20)
            relevant  = [
                h for h in open_hyps
                if any(
                    kw in (h["subject"] + " " + (h["object"] or "")).lower()
                    for kw in _extract_keywords(user_text)
                )
            ][:3]
            if relevant:
                hyp_lines = []
                for h in relevant:
                    hyp_lines.append(
                        f"  {h['subject']} may {h['relation_type'].lower()} "
                        f"{h['object'] or '?'} (unconfirmed)"
                    )
                sections.append("OPEN HYPOTHESES:\n" + "\n".join(hyp_lines))
        except Exception:
            pass

        # ── Recent memory passages ─────────────────────────────────────
        try:
            topic    = " ".join(_extract_keywords(user_text)[:2]) or user_text[:40]
            results  = self._brain.memory.search(topic, top_k=3)
            passages = []
            for _k, m in results:
                snippet = (m.content or "").strip()[:150]
                if snippet:
                    passages.append(f"  \"{snippet}\"")
            if passages:
                sections.append("RECENT MEMORY:\n" + "\n".join(passages))
        except Exception:
            pass

        # ── Latest reflection ──────────────────────────────────────────
        try:
            ref = self._brain.consolidation.latest_reflection()
            if ref and ref.get("reflection"):
                snippet = ref["reflection"][:250].strip()
                sections.append(f'LATEST REFLECTION: "{snippet}..."')
        except Exception:
            pass

        # ── Curiosity frontier ─────────────────────────────────────────
        try:
            gaps: list[str] = []
            for r in self._brain.curiosity_report():
                if not r.get("already_fetched"):
                    gaps.append(r["concept"])
            if gaps:
                sections.append(f"OPEN CURIOSITIES: {', '.join(gaps[:4])}")
        except Exception:
            pass

        # ── Active goals (M29) ─────────────────────────────────────────
        # Grounds "what are you trying to learn?" in the actual goal set.
        try:
            report = self._brain.goal_report()
            active = report.get("active", [])
            if active:
                lines = [f"- {g.statement} (origin: {g.origin})"
                         for g in active[:5]]
                sections.append("ACTIVE GOALS (persistent intentions):\n"
                                + "\n".join(lines))
        except Exception:
            pass

        # ── Recent decisions (M28) ─────────────────────────────────────
        # Grounds "what have you been deciding?" in the actual DecisionLog
        # rather than letting the model improvise.
        try:
            decisions = self._brain.recent_decisions(n=5)
            if decisions:
                lines = [f"- [{d.subsystem}] {d.decision}" for d in decisions]
                sections.append("RECENT DECISIONS (newest first):\n"
                                + "\n".join(lines))
        except Exception:
            pass

        return "\n\n".join(sections) if sections else "(no state available)"

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, conversation: list[dict], user_text: str,
                      state_ctx: str) -> str:
        """
        Assemble the full prompt. State goes first; prior turns provide thread.
        """
        lines: list[str] = [
            "=== GENESIS STATE ===",
            state_ctx,
            "",
            "=== CONVERSATION SO FAR ===",
        ]

        # Prior turns (all of them — current user message is appended separately)
        for turn in conversation:
            speaker = "Human" if turn["role"] == "user" else "Genesis"
            lines.append(f"{speaker}: {turn['text']}")

        lines += [
            "",
            f"Human: {user_text}",
            "",
            "Genesis:",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Local LLM call
    # ------------------------------------------------------------------

    def _call_local(self, prompt: str) -> str:
        """
        POST to the OpenAI-compatible local endpoint.
        Returns empty string on any failure.
        """
        try:
            import requests  # already in project deps via web module
        except ImportError:
            self._log("voice_llm.import", ImportError("requests not available"))
            return ""

        payload = {
            "model":       self._model,
            "messages":    [
                {"role": "system",  "content": _SYSTEM},
                {"role": "user",    "content": prompt},
            ],
            "stream":      False,
            "max_tokens":  _MAX_TOKENS,
            "temperature": 0.7,
        }

        try:
            resp = requests.post(
                f"{self._url}/chat/completions",
                json=payload,
                timeout=_TIMEOUT_S,
            )
            resp.raise_for_status()
            data    = resp.json()
            content = data["choices"][0]["message"]["content"]
            return (content or "").strip()
        except Exception as exc:
            self._log("voice_llm.call", exc)
            return ""

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Ping the local server to see if it's running."""
        try:
            import requests
            resp = requests.get(
                f"{self._url.replace('/v1', '')}/api/tags",
                timeout=2,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _log(self, label: str, exc: Exception) -> None:
        try:
            self._brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            pass


# ── Helpers ────────────────────────────────────────────────────────────────────

_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "do", "does", "did",
    "you", "your", "what", "how", "why", "when", "where", "who", "which",
    "about", "that", "this", "with", "from", "have", "has", "had", "can",
    "tell", "me", "i", "my", "we", "our", "it", "its", "be", "been",
    "any", "of", "to", "in", "on", "at", "and", "or", "but", "not",
}


def _extract_keywords(text: str) -> list[str]:
    """Simple keyword extraction — content words, lowercased, stop-words removed."""
    import re
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 2]


def _interpret_drives(d: dict) -> str:
    """Plain-language summary of what Genesis's drives mean right now."""
    notes: list[str] = []
    if d.get("hunger",       0) > 0.6:
        notes.append("strong appetite for new input")
    if d.get("frustration",  0) > 0.5:
        notes.append("something isn't resolving")
    if d.get("anticipation", 0) > 0.6:
        notes.append("something building")
    if d.get("boredom",      0) > 0.5:
        notes.append("not enough novelty")
    if d.get("dissonance",   0) > 0.5:
        notes.append("holding unresolved contradictions")
    return "; ".join(notes) if notes else "drives balanced"
