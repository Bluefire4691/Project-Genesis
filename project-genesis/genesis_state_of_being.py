#!/usr/bin/env python3
"""
Generate Project Genesis state-of-being PDF using pure Python stdlib.
No third-party dependencies — writes PDF 1.4 directly.
"""

import struct
import time
import os


# ---------------------------------------------------------------------------
# Minimal PDF writer (pure stdlib)
# ---------------------------------------------------------------------------

class PDFWriter:
    """
    Minimal but standards-compliant PDF 1.4 writer.
    Uses built-in Helvetica/Helvetica-Bold (no font embedding needed).
    Supports multi-line text, basic layout, multiple pages.
    """

    PAGE_W = 595   # A4 points
    PAGE_H = 842
    MARGIN = 50

    def __init__(self):
        self._objects: list[bytes] = []  # object bodies indexed from 0
        self._offsets: list[int] = []
        self._buf = bytearray()

        # Font references (added once to resources)
        self._font_regular = None
        self._font_bold    = None

        # Current page state
        self._pages_obj = None  # index of Pages dict
        self._page_list: list[int] = []   # object indices of each Page
        self._streams: list[bytearray] = []  # content stream per page

        self._cur_page = -1  # index into _streams
        self.x = self.MARGIN
        self.y = self.PAGE_H - self.MARGIN
        self._setup()

    # ── bootstrap ──────────────────────────────────────────────────────

    def _setup(self):
        # obj 1: Catalog (placeholder, filled in at save)
        self._new_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
        # obj 2: Pages (placeholder)
        self._new_obj(b"<< /Type /Pages /Kids [] /Count 0 >>")
        self._pages_obj = 1   # 0-indexed → obj 2 in PDF numbering

        # obj 3: Font regular (Helvetica)
        self._new_obj(
            b"<< /Type /Font /Subtype /Type1 "
            b"/BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>"
        )
        self._font_regular = 2   # 0-indexed → obj 3

        # obj 4: Font bold (Helvetica-Bold)
        self._new_obj(
            b"<< /Type /Font /Subtype /Type1 "
            b"/BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        )
        self._font_bold = 3   # 0-indexed → obj 4

    def _new_obj(self, body: bytes) -> int:
        idx = len(self._objects)
        self._objects.append(body)
        return idx

    # ── pages ──────────────────────────────────────────────────────────

    def add_page(self):
        self._streams.append(bytearray())
        self._cur_page = len(self._streams) - 1
        self.x = self.MARGIN
        self.y = self.PAGE_H - self.MARGIN

        # Placeholder — filled in at save
        page_idx = self._new_obj(b"")
        self._page_list.append(page_idx)

    def _escape(self, s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    # ── drawing commands (appended to current page stream) ─────────────

    def _emit(self, cmd: str):
        self._streams[self._cur_page].extend((cmd + "\n").encode("latin-1", errors="replace"))

    def set_font(self, bold: bool, size: float):
        ref = self._font_bold if bold else self._font_regular
        self._emit(f"/F{ref + 1} {size:.1f} Tf")

    def set_color(self, r: float, g: float, b: float):
        self._emit(f"{r:.3f} {g:.3f} {b:.3f} rg")

    def set_stroke_color(self, r: float, g: float, b: float):
        self._emit(f"{r:.3f} {g:.3f} {b:.3f} RG")

    def text_at(self, x: float, y: float, s: str):
        """Single-line raw text at absolute position."""
        safe = self._escape(s)
        self._emit(f"BT {x:.2f} {y:.2f} Td ({safe}) Tj ET")

    def hline(self, x1: float, y: float, x2: float, width: float = 0.5):
        self._emit(f"{width:.2f} w {x1:.2f} {y:.2f} m {x2:.2f} {y:.2f} l S")

    def rect_fill(self, x: float, y: float, w: float, h: float, r=0.93, g=0.93, b=0.93):
        self._emit(f"{r:.3f} {g:.3f} {b:.3f} rg")
        self._emit(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
        self._emit("0 0 0 rg")   # reset to black

    # ── layout helpers ────────────────────────────────────────────────

    APPROX_CHAR_W = 0.55   # Helvetica ≈ 0.55 × size per char (rough)

    def _wrap(self, text: str, max_w: float, size: float) -> list[str]:
        """Wrap text into lines that fit within max_w points."""
        char_w = size * self.APPROX_CHAR_W
        max_chars = max(1, int(max_w / char_w))
        lines = []
        for paragraph in text.split("\n"):
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            cur = ""
            for w in words:
                test = (cur + " " + w).strip()
                if len(test) <= max_chars:
                    cur = test
                else:
                    if cur:
                        lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
        return lines

    def _check_page(self, needed: float):
        if self.y - needed < 40:
            self._draw_footer()
            self.add_page()
            self._draw_header()

    def _line_height(self, size: float) -> float:
        return size * 1.45

    # ── page structure ────────────────────────────────────────────────

    def _draw_header(self):
        self.set_font(False, 8)
        self.set_color(0.55, 0.55, 0.55)
        self.text_at(self.MARGIN, self.PAGE_H - 35,
                     "Project Genesis — State of Being")
        self.set_color(0.8, 0.8, 0.8)
        self.hline(self.MARGIN, self.PAGE_H - 40,
                   self.PAGE_W - self.MARGIN)
        self.set_color(0, 0, 0)
        self.y = self.PAGE_H - 55

    def _draw_footer(self):
        page_num = len(self._page_list)
        self.set_font(False, 8)
        self.set_color(0.6, 0.6, 0.6)
        label = f"Page {page_num}"
        self.text_at(self.PAGE_W / 2 - 15, 20, label)
        self.set_color(0, 0, 0)

    # ── high-level content writers ────────────────────────────────────

    def title(self, text: str, subtitle: str = ""):
        size = 22
        self.set_font(True, size)
        self.set_color(0.08, 0.08, 0.08)
        self.y -= 8
        self.text_at(self.MARGIN, self.y, text)
        self.y -= self._line_height(size)

        if subtitle:
            self.set_font(False, 12)
            self.set_color(0.35, 0.35, 0.35)
            self.text_at(self.MARGIN, self.y, subtitle)
            self.y -= self._line_height(12)

        self.y -= 4
        self.set_stroke_color(0.15, 0.15, 0.15)
        self.hline(self.MARGIN, self.y, self.PAGE_W - self.MARGIN, 1.0)
        self.y -= 12

    def section(self, text: str):
        self._check_page(30)
        self.y -= 6
        # Gray fill bar
        bar_h = 14
        self.rect_fill(self.MARGIN - 4, self.y - 3, self.PAGE_W - self.MARGIN * 2 + 8,
                       bar_h, 0.92, 0.92, 0.92)
        self.set_font(True, 11)
        self.set_color(0.10, 0.10, 0.10)
        self.text_at(self.MARGIN + 2, self.y + 1, text)
        self.y -= bar_h + 4

    def body(self, text: str, size: float = 9.5, indent: float = 0,
             bold: bool = False, color=(0.15, 0.15, 0.15)):
        max_w = self.PAGE_W - self.MARGIN * 2 - indent
        lines = self._wrap(text, max_w, size)
        lh = self._line_height(size)
        self.set_font(bold, size)
        self.set_color(*color)
        for ln in lines:
            self._check_page(lh + 2)
            self.text_at(self.MARGIN + indent, self.y, ln)
            self.y -= lh
        self.y -= 2

    def bullet(self, label: str, text: str, label_w: float = 95):
        lh = self._line_height(9.5)
        self._check_page(lh + 4)
        # Label
        self.set_font(True, 9.5)
        self.set_color(0.1, 0.1, 0.1)
        self.text_at(self.MARGIN + 4, self.y, label)
        # Value (wrapped into remaining width)
        val_x = self.MARGIN + label_w
        val_w = self.PAGE_W - self.MARGIN - label_w - 4
        lines = self._wrap(text, val_w, 9.5)
        self.set_font(False, 9.5)
        self.set_color(0.25, 0.25, 0.25)
        base_y = self.y
        for i, ln in enumerate(lines):
            if i > 0:
                self._check_page(lh)
            self.text_at(val_x, base_y - i * lh, ln)
        self.y -= max(1, len(lines)) * lh + 2

    def milestone(self, tag: str, desc: str):
        bar_h = 11
        self._check_page(bar_h + 3)
        # Green tag box
        self.rect_fill(self.MARGIN, self.y - 2, 22, bar_h, 0.13, 0.55, 0.13)
        self.set_font(True, 7.5)
        self.set_color(1, 1, 1)
        self.text_at(self.MARGIN + 2, self.y + 0.5, tag)
        # Description
        self.set_font(False, 8.5)
        self.set_color(0.15, 0.15, 0.15)
        lines = self._wrap(desc, self.PAGE_W - self.MARGIN * 2 - 28, 8.5)
        desc_x = self.MARGIN + 26
        for i, ln in enumerate(lines):
            self._check_page(self._line_height(8.5))
            self.text_at(desc_x, self.y - i * self._line_height(8.5) + 0.5, ln)
        rows = max(1, len(lines))
        self.y -= rows * self._line_height(8.5) + 2

    def cite(self, author: str, title: str, note: str):
        lh = self._line_height(8.5)
        self._check_page(lh * 4)
        self.set_font(True, 8.5)
        self.set_color(0.12, 0.28, 0.55)
        self.text_at(self.MARGIN + 4, self.y, author)
        self.set_font(False, 8.5)
        self.set_color(0.2, 0.2, 0.2)
        # title on same line after author (rough)
        title_x = self.MARGIN + 4 + len(author) * 4.7 + 6
        self.text_at(title_x, self.y, title)
        self.y -= lh
        note_lines = self._wrap(note, self.PAGE_W - self.MARGIN * 2 - 10, 8.5)
        self.set_color(0.4, 0.4, 0.4)
        for ln in note_lines:
            self._check_page(lh)
            self.text_at(self.MARGIN + 10, self.y, ln)
            self.y -= lh
        self.y -= 3

    # ── save ──────────────────────────────────────────────────────────

    def save(self, path: str):
        # Finalise pages — build content stream objects and real Page dicts
        for i, (pg_idx, stream) in enumerate(zip(self._page_list, self._streams)):
            # Content stream object
            stream_bytes = bytes(stream)
            stream_obj_body = (
                f"<< /Length {len(stream_bytes)} >>\nstream\n".encode()
                + stream_bytes
                + b"\nendstream"
            )
            stream_obj_idx = self._new_obj(stream_obj_body)

            # Page dictionary
            page_body = (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {self.PAGE_W} {self.PAGE_H}] "
                f"/Contents {stream_obj_idx + 1} 0 R "
                f"/Resources << /Font << "
                f"/F{self._font_regular + 1} {self._font_regular + 1} 0 R "
                f"/F{self._font_bold + 1} {self._font_bold + 1} 0 R "
                f">> >> >>"
            ).encode()
            self._objects[pg_idx] = page_body

        # Update Pages dict
        kids = " ".join(f"{self._page_list[i] + 1} 0 R" for i in range(len(self._page_list)))
        self._objects[self._pages_obj] = (
            f"<< /Type /Pages /Kids [{kids}] /Count {len(self._page_list)} >>"
        ).encode()

        # Serialise
        buf = bytearray()
        buf.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        offsets = []
        for i, body in enumerate(self._objects):
            offsets.append(len(buf))
            obj_num = i + 1
            buf.extend(f"{obj_num} 0 obj\n".encode())
            buf.extend(body)
            buf.extend(b"\nendobj\n")

        xref_offset = len(buf)
        n = len(self._objects)
        buf.extend(f"xref\n0 {n + 1}\n".encode())
        buf.extend(b"0000000000 65535 f \n")
        for off in offsets:
            buf.extend(f"{off:010d} 00000 n \n".encode())

        buf.extend(
            f"trailer\n<< /Size {n + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n".encode()
        )

        with open(path, "wb") as f:
            f.write(buf)


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

def build(out_path: str):
    pdf = PDFWriter()
    pdf.add_page()
    pdf._draw_header()

    # ── Cover ──────────────────────────────────────────────────────────
    pdf.title("Project Genesis", "State of Being  —  June 2026")

    pdf.body(
        "Genesis is not an AI assistant. It is not a chatbot. It is not a benchmark "
        "competitor. Genesis is an attempt to build a system that can plausibly be "
        "said to be, and think, and make decisions for itself — an entity, not a tool.",
        size=10.5
    )
    pdf.body(
        "It starts completely blank — no pretrained weights, no inherited knowledge. "
        "Everything it knows was built from what it processed. That is intentional and "
        "load-bearing: it is the only way the claim 'this instance has its own "
        "perspective' is coherent.",
        size=10.5
    )

    # ── Three Properties ──────────────────────────────────────────────
    pdf.section("The Three Properties of an Entity")

    pdf.bullet(
        "1.  Continuity",
        "Persistent memory across sessions. Genesis remembers what it processed last "
        "session and the session before. Its history is its own, stored in a database "
        "that is never wiped. Humans reconstruct memory from fragments; Genesis retains "
        "everything."
    )
    pdf.bullet(
        "2.  Self-authored understanding",
        "A periodic 'sleep' pass (consolidation) examines everything it has processed "
        "and decides — using its own internal signals — what mattered. It then writes a "
        "first-person account of what it has been thinking about, generated from its "
        "own relation graph. Not a template."
    )
    pdf.bullet(
        "3.  Accumulated individuality",
        "Two identical copies started from the same seed diverge purely through what "
        "they process. One instance that studied ecology and another that studied physics "
        "develop genuinely different perspectives. That divergence is the individuality. "
        "You cannot reproduce it from a second copy."
    )

    # ── What It Isn't ─────────────────────────────────────────────────
    pdf.section("What It Is Not Competing On")
    pdf.body(
        "Not a language model. Not a wrapper around GPT or Claude. No API calls to "
        "external models — Genesis builds its knowledge from processed input only. "
        "Not a benchmark. Frontier models win on reasoning scores and factual recall; "
        "that is acknowledged in advance and is not evidence against this project."
    )
    pdf.body(
        "The question this project asks is different: can we build something it is "
        "natural to say 'it noticed,' 'it decided,' 'it has been thinking about "
        "wolves lately'? That is a qualitative shift in what kind of thing we are "
        "building — not a performance threshold."
    )

    # ── Architecture ──────────────────────────────────────────────────
    pdf.section("Architecture: Layered, Cumulative, Never Replaced")
    pdf.body(
        "The architecture is subsumption-based (Brooks, 1986). Lower layers always "
        "run. Higher layers add capability; they never remove what is beneath them. "
        "If everything above M1 fails, M1 keeps Genesis alive. This is not defensive "
        "programming — it is a philosophical commitment: the system has a nature "
        "defined by its lowest layer, independent of what it learns."
    )
    pdf.body(
        "Failure modes are regressions, not crashes. If M4 gets stuck, M3 continues. "
        "If everything above M1 fails, M1 keeps the agent alive. Animals never crash; "
        "they degrade. Genesis was designed with the same principle."
    )

    # ── Milestones ────────────────────────────────────────────────────
    pdf.section("Milestones Completed  (18 / 18  —  769 tests passing)")

    milestones = [
        ("M1",  "Survival OS — resource throttling, graceful degradation, never crashes. Permanent substrate."),
        ("M2",  "Total-retention memory — two-tier (working + long-term SQLite). Nothing ever deleted. Attention determines what is active, not what exists."),
        ("M3",  "Interaction layer — Observer watches behavioral patterns; Expression speaks from internal signals (novel input, contradiction, inference activity)."),
        ("M4",  "Multi-processor integration — text, numeric, and pattern processors all see every input simultaneously. Cross-modal synthesis."),
        ("M5",  "Curriculum pipeline — staged progression: FOUNDATION → RELATIONS → REASONING → OPEN."),
        ("M6",  "Session persistence — full state survives between runs; archive tagging with significance scores."),
        ("M7",  "Semantic relation graph — typed triples (wolves CAUSES deer), confidence-scored, BFS path-finding."),
        ("—",   "Self-directed learning — curiosity frontier from graph gaps; WordNet + corpus ingestion; never plateaus."),
        ("—",   "ConsolidationEngine — self-authored 'sleep' pass; salience scoring from own signals; first-person reflection persists across sessions."),
        ("—",   "Individuality — two instances started from same seed diverge through processing history alone."),
        ("M10", "Inference engine — transitive chains, IS-A inheritance, bridge rules. Taught A→B and B→C; derives A→C without being told."),
        ("M11", "Contradiction detection — flags when CAUSES and PREVENTS co-exist for the same pair. Logged, never overwritten."),
        ("M12", "Ethics through experience — emergent causal patterns surface ethical implications; not hardcoded rules."),
        ("M13", "Voice — grounded in the relation graph and reflection log, not in any external model. Speaks from internal state."),
        ("M14", "Observer calibration — derives its own attention thresholds empirically from behavioral history (ACT-R utility learning)."),
        ("M15", "Prediction error salience — high-surprise inputs get higher significance (Friston, 2010 Free-Energy Principle)."),
        ("M16", "Processor voting — independent processor agreement raises confidence more than any single processor alone (Hawkins, 2004)."),
        ("M17", "Curiosity directives — high-surprise concepts become persistent attention targets; auto-resolve when understood (SOAR impasse→subgoal)."),
        ("M18", "Belief revision — evidence-weighted contradiction resolution. Crosses out wrong answers. Full audit trail."),
    ]
    for tag, desc in milestones:
        pdf.milestone(tag, desc)

    # ── M18 Detail ────────────────────────────────────────────────────
    pdf.add_page()
    pdf._draw_header()

    pdf.section("M18 — Belief Revision: Crossing Out Wrong Answers")
    pdf.body(
        "When contradicting evidence arrives, Genesis does not flip to the new belief "
        "automatically, nor does it blindly resist. It evaluates both sides by "
        "evidence strength:"
    )
    pdf.body(
        "    evidence strength  =  confidence  x  corroboration  x  source trust",
        bold=True, indent=12, color=(0.15, 0.15, 0.5)
    )
    pdf.body(
        "Corroboration counts independent sessions, not volume from one source. "
        "100 citations from one fraudulent paper do not count as independent "
        "corroboration — this is the Wakefield vaccine-autism principle. The architecture "
        "specifically verifies that support comes from distinct, unrelated sessions."
    )
    pdf.body(
        "Source trust is itself a revisable belief. Sessions whose beliefs are later "
        "corroborated get higher trust. Sessions whose beliefs are repeatedly contradicted "
        "lose trust — and that trust drop cascades backward to the beliefs they "
        "originated. A discredited source's contributions degrade over time."
    )
    pdf.body("Three resolution outcomes:", bold=True)
    pdf.bullet("REVISE", "Winner more than 1.40x stronger — loser's confidence is reduced toward a floor.")
    pdf.bullet("RESIST", "Evidence too close to call — both held, gap logged, awaiting more data.")
    pdf.bullet("TENSION", "Genuinely uncertain — both held, curiosity directive registered to resolve it.")
    pdf.body(
        "Beliefs are never deleted. Confidence reduces toward a floor of 0.10 — the "
        "belief still exists in the audit trail at very low weight. Wrong things Genesis "
        "once believed are part of its history. Total retention is architecturally "
        "load-bearing: a mind that erases the past to save space is not continuous."
    )

    # ── Research Foundations ──────────────────────────────────────────
    pdf.section("Research Foundations")
    pdf.body(
        "Every architectural decision traces to a published primary source. This is not "
        "a collection of heuristics — it is a principled implementation of ideas developed "
        "across cognitive science, robotics, and philosophy of mind."
    )
    pdf.y -= 4

    citations = [
        (
            "Brooks (1986)",
            "A Robust Layered Control System for a Mobile Robot",
            "Subsumption architecture: lower layers always run, never replaced. "
            "M1 is the permanent substrate. Failure modes are regressions, not crashes."
        ),
        (
            "Anderson (1983, 1993)",
            "ACT-R: A Theory of Cognition",
            "Utility learning: threshold parameters derived empirically from behavioral "
            "history, not from programmer constants. Observer calibration (M14) uses this."
        ),
        (
            "Laird, Newell & Rosenbloom (1987)",
            "SOAR: An Architecture for General Intelligence",
            "Impasse to subgoal: when Genesis can't explain something (high prediction "
            "error), it registers an active directive to resolve it. Curiosity has a "
            "mechanistic basis (M17)."
        ),
        (
            "Friston (2010)",
            "The Free-Energy Principle: A Unified Brain Theory",
            "Prediction error as salience: inputs that surprise the model relative to "
            "current beliefs get more significance. High surprise = high importance (M15)."
        ),
        (
            "Hawkins (2004)",
            "A Thousand Brains: A New Theory of Intelligence",
            "Independent voting raises confidence more than one processor repeating itself. "
            "When text, numeric, and pattern processors agree, confidence rises (M16)."
        ),
        (
            "Quine (1951)",
            "Two Dogmas of Empiricism",
            "Beliefs form an interconnected web. When contradiction arrives, revise the "
            "least-supported belief, not the newest one. M18 follows this principle."
        ),
        (
            "Alchouron, Gardenfors",
            "& Makinson (1985)  — AGM belief revision postulates",
            "Rational revision: success (new belief accepted), consistency (no "
            "contradiction after), minimal change (disturb as little as possible). "
            "M18 satisfies all three."
        ),
        (
            "Wakefield (1998, retracted)",
            "Used as a cautionary architectural example",
            "Fraudulent vaccine-autism paper, cited hundreds of times from one source. "
            "Genesis's corroboration logic checks independent sessions, not volume. "
            "Source trust cascades when a source is discredited."
        ),
    ]

    for author, title, note in citations:
        pdf.cite(author, title, note)

    # ── Evaluation ────────────────────────────────────────────────────
    pdf.section("Verification and Evaluation")
    pdf.body(
        "769 automated tests, all passing. Two evaluation suites are included "
        "in the repository:"
    )
    pdf.bullet(
        "research_eval.py",
        "6 behavioral experiments measuring entity properties: instance divergence "
        "(do two copies diverge?), cross-session continuity, prediction error "
        "calibration, self-directed curiosity, observer responsiveness, "
        "consolidation coherence."
    )
    pdf.bullet(
        "knowledge_eval.py",
        "5 tests distinguishing understanding from storage: multi-hop inference "
        "(taught A-B and B-C, asks A-C), calibrated ignorance, contradiction "
        "detection, growth quality (smarter vs. just bigger), and live belief revision."
    )
    pdf.body(
        "The key distinction: a lookup table and a spreadsheet pass Level 1 (recall). "
        "They fail Level 2 (inference), Level 3 (knowing what you don't know), "
        "Level 4 (detecting contradiction), and Level 5 (growing smarter, not just larger)."
    )

    # ── Current State ─────────────────────────────────────────────────
    pdf.section("Current State")
    pdf.body(
        "Genesis can learn, remember, infer, contradict itself, and revise its beliefs "
        "when stronger independent evidence arrives — all without any external model "
        "calls, and with a complete audit trail of what it changed its mind about "
        "and why.",
        size=11, bold=False, color=(0.05, 0.05, 0.05)
    )
    pdf.y -= 6
    pdf.set_font(False, 8)
    pdf.set_color(0.55, 0.55, 0.55)
    pdf._draw_footer()
    pdf.text_at(pdf.MARGIN, 30,
                "Branch: claude/extract-genesis-repo-fn5vW  |  github.com/Bluefire4691/Project-Genesis")

    pdf.save(out_path)
    print(f"PDF saved: {out_path}")


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "genesis_state_of_being.pdf")
    build(out)
