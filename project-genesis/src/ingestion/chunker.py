"""
Text Chunker — Ingestion Pipeline.

Splits long article text into segments sized for the TextProcessor.
The processor works best on 2-4 sentence chunks — long enough to
contain relational context, short enough to extract clean triples.

Filters out: section headers, reference noise, very short fragments,
and Wikipedia boilerplate that won't produce meaningful relations.
"""

import re
from typing import Iterator


_MIN_CHUNK_CHARS = 60    # shorter than this → skip
_MAX_CHUNK_CHARS = 500   # split longer chunks further
_SENTENCES_PER_CHUNK = 3


def chunk_text(text: str, sentences_per_chunk: int = _SENTENCES_PER_CHUNK) -> list[str]:
    """
    Split article text into processor-ready chunks.

    Each chunk is 2-4 sentences of clean prose. Headers, references,
    and boilerplate are stripped before splitting.
    """
    cleaned = _clean(text)
    sentences = _split_sentences(cleaned)
    return list(_group(sentences, sentences_per_chunk))


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

def _clean(text: str) -> str:
    """Remove Wikipedia markup, headers, and reference noise."""
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
    """Split text into individual sentences, filtering noise."""
    # Split on sentence-ending punctuation followed by space + capital
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", text)
    sentences = []
    for s in raw:
        s = s.strip()
        # Skip too short, too long (likely a malformed chunk), or header-like
        if len(s) < _MIN_CHUNK_CHARS:
            continue
        if s.startswith("==") or s.startswith("*") or s.startswith("#"):
            continue
        # Skip lines that are mostly numbers or punctuation (tables, etc.)
        alpha_ratio = sum(c.isalpha() for c in s) / max(1, len(s))
        if alpha_ratio < 0.5:
            continue
        sentences.append(s)
    return sentences


def _group(sentences: list[str], n: int) -> Iterator[str]:
    """Yield non-overlapping groups of n sentences as single strings."""
    for i in range(0, len(sentences), n):
        group = sentences[i:i + n]
        chunk = " ".join(group)
        if len(chunk) >= _MIN_CHUNK_CHARS:
            # If a single chunk is very long, split it further
            if len(chunk) > _MAX_CHUNK_CHARS and len(group) > 1:
                # Yield first half and second half separately
                mid = len(group) // 2
                a = " ".join(group[:mid])
                b = " ".join(group[mid:])
                if len(a) >= _MIN_CHUNK_CHARS:
                    yield a
                if len(b) >= _MIN_CHUNK_CHARS:
                    yield b
            else:
                yield chunk
