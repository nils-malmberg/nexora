"""Controlled extractive summarization.

Operates strictly on the title/excerpt already provided by the source -
never fetches or invents additional text - so the result can never add
information the source did not already state (specs/NEWS_AND_EVENTS.md:
"ne pas ajouter d'information non étayée"). On any failure to produce a
useful summary, the caller falls back to the original title/excerpt rather
than inventing one.
"""

from __future__ import annotations

import re
from collections import Counter

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-zà-öø-ÿ0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "is", "are", "was", "were",
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "ou", "est", "sont", "pour", "dans",
    "en", "au", "aux", "avec", "sur", "par", "que", "qui",
}
SHORT_ENOUGH_LEN = 280
MAX_SUMMARY_LEN = 400
MAX_SENTENCES = 2


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOPWORDS]


def summarize(title: str, excerpt: str | None) -> str | None:
    if not excerpt:
        return None
    excerpt = excerpt.strip()
    if not excerpt:
        return None
    if len(excerpt) <= SHORT_ENOUGH_LEN:
        return excerpt

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(excerpt) if s.strip()]
    if len(sentences) <= MAX_SENTENCES:
        result = " ".join(sentences)
        return result[:MAX_SUMMARY_LEN]

    title_tokens = Counter(_tokenize(title))
    scored = []
    for position, sentence in enumerate(sentences):
        tokens = _tokenize(sentence)
        if not tokens:
            continue
        overlap = sum(title_tokens.get(t, 0) for t in tokens)
        position_bonus = 1.0 if position == 0 else 0.0
        scored.append((overlap / len(tokens) + position_bonus, position, sentence))

    if not scored:
        return excerpt[:MAX_SUMMARY_LEN]

    top = sorted(scored, key=lambda x: x[0], reverse=True)[:MAX_SENTENCES]
    picked_positions = {pos for _, pos, _ in top}
    ordered_sentences = [sentences[i] for i in range(len(sentences)) if i in picked_positions]
    return " ".join(ordered_sentences)[:MAX_SUMMARY_LEN]
