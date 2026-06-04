"""
Text Chunker — Ingestion Pipeline.

Groups long source text into segments sized for the TextProcessor while
PRESERVING the structure that carries meaning.

Design principle (load-bearing): never discard a sentence for being short.
Short declarative sentences — "Wolves hunt deer." "Grass needs rain." — carry
the cleanest causal and categorical structure in the whole text. The previous
implementation dropped every sentence under 60 characters, which threw away
exactly the relations worth extracting and severed discourse links (anaphora,
"which in turn", "as a result") from their referents.

What this chunker does:
    - Strips genuine noise: markup headers, reference markers, tables/number
      runs, pronunciation-guide parentheticals.
    - Splits into whole sentences. NO length floor — short sentences are kept.
    - Groups CONSECUTIVE sentences (in order) into chunks under a character
      budget, so cross-sentence context stays together. Sentences are never
      split apart and never dropped.

Total retention applies here too: cleaning removes only formatting noise that
was never language, not content.
"""

import re
from typing import Iterator


# Target number of sentences per chunk — a soft target. A chunk may hold fewer
# (end of text) or be split earlier if it would exceed the character budget.
_SENTENCES_PER_CHUNK = 3

# Hard character ceiling per chunk — keeps the TextProcessor input bounded.
# Sentences are kept whole; a group is flushed before it crosses this.
_MAX_CHUNK_CHARS = 600


def chunk_text(text: str, sentences_per_chunk: int = _SENTENCES_PER_CHUNK) -> list[str]:
    """
    Split source text into processor-ready chunks without losing structure.

    Each chunk is a run of consecutive whole sentences. No sentence is dropped
    for length; only formatting noise is removed during cleaning.
    """
    cleaned = _clean(text)
    sentences = _split_sentences(cleaned)
    return list(_group(sentences, sentences_per_chunk))


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

def _clean(text: str) -> str:
    """Remove markup, headers, and reference noise — formatting, not content."""
    # Section headers (== Heading ==)
    text = re.sub(r"={2,}[^=]+=={2,}", " ", text)
    # Reference markers [1], [2], etc.
    text = re.sub(r"\[\d+\]", "", text)
    # Parenthetical pronunciation guides (often long and noisy)
    text = re.sub(r"\([^)]{40,}\)", "", text)
    # Multiple whitespace → single space
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    """
    Split text into individual sentences, filtering only true noise.

    A sentence is kept regardless of length. It is dropped only if it is
    structural noise: a markup header, or a line that is mostly digits and
    punctuation (a table row, citation block, or formatting artifact).
    """
    # Split on sentence-ending punctuation followed by space + capital/quote.
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", text)
    sentences: list[str] = []
    for s in raw:
        s = s.strip()
        if not s:
            continue
        # Markup/header artifacts — never language.
        if s.startswith("==") or s.startswith("*") or s.startswith("#"):
            continue
        # Drop lines that are mostly numbers or punctuation (tables, refs).
        # Short prose sentences pass this easily; only number/punct runs fail.
        alpha_ratio = sum(c.isalpha() for c in s) / max(1, len(s))
        if alpha_ratio < 0.5:
            continue
        # A "sentence" with no real word at all is noise.
        if not any(len(tok) >= 2 and tok.isalpha() for tok in re.findall(r"[A-Za-z]+", s)):
            continue
        sentences.append(s)
    return sentences


def _group(sentences: list[str], n: int) -> Iterator[str]:
    """
    Yield groups of consecutive whole sentences.

    A group accumulates up to `n` sentences, but is flushed early if adding the
    next sentence would push it past the character ceiling. Sentences are kept
    intact and in order — context that spans sentences stays in the same chunk.
    No sentence is ever dropped.
    """
    n = max(1, n)
    group: list[str] = []
    length = 0

    for sent in sentences:
        slen = len(sent) + 1  # +1 for the joining space
        # Flush if the group is full, or adding this sentence would overflow
        # the ceiling (but always allow at least one sentence per group).
        if group and (len(group) >= n or length + slen > _MAX_CHUNK_CHARS):
            yield " ".join(group)
            group, length = [], 0
        group.append(sent)
        length += slen

    if group:
        yield " ".join(group)
