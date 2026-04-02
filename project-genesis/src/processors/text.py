"""
Text sensory processor.

Handles text input: tokenization, keyword extraction, basic sentiment
classification, and category identification. Uses heuristics, not neural nets.
"""

import re
from typing import Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import ProcessorOutput
from processors.base import BaseProcessor


class TextProcessor(BaseProcessor):
    name = "text"

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

    STOPWORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                 "being", "have", "has", "had", "do", "does", "did", "will",
                 "would", "could", "should", "may", "might", "can", "shall",
                 "it", "its", "this", "that", "and", "but", "or", "not", "no",
                 "in", "on", "at", "to", "for", "of", "with", "by", "from",
                 "as", "into", "about", "than", "then", "so", "if", "when"}

    def _process(self, data: Any) -> ProcessorOutput:
        text = str(data)  # Coerce anything to string — never reject input
        words = set(re.findall(r'\b\w+\b', text.lower()))

        keywords = [w for w in words if w not in self.STOPWORDS and len(w) >= 3]

        categories = []
        for cat, cat_words in self.CATEGORIES.items():
            if words & cat_words:
                categories.append(cat)

        pos_count = len(words & self.POSITIVE)
        neg_count = len(words & self.NEGATIVE)
        if pos_count > neg_count:
            sentiment = "positive"
        elif neg_count > pos_count:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        importance = min(1.0, len(keywords) * 0.08 + (0.1 if sentiment != "neutral" else 0))

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
