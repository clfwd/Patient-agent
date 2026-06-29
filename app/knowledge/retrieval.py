"""Keyword retrieval helpers for local medical knowledge."""

import re


WORD_RE = re.compile(r"[a-z0-9]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
ENGLISH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
}


def normalize_text(value):
    return " ".join(str(value or "").lower().split())


def tokenize_query(query):
    text = normalize_text(query)
    tokens = set(
        item
        for item in WORD_RE.findall(text)
        if len(item) >= 3 and item not in ENGLISH_STOPWORDS
    )
    for phrase in CJK_RE.findall(text):
        if len(phrase) <= 4:
            tokens.add(phrase)
        for index in range(0, max(len(phrase) - 1, 0)):
            tokens.add(phrase[index : index + 2])
    return [token for token in tokens if token]


def score_text(query_tokens, search_text):
    text = normalize_text(search_text)
    if not query_tokens or not text:
        return 0
    score = 0
    for token in query_tokens:
        if token in text:
            score += 3 if len(token) > 2 else 2
    return score


def rank_chunks(query, chunks, limit=3):
    tokens = tokenize_query(query)
    ranked = []
    for chunk in chunks:
        document = chunk.document
        search_text = " ".join(
            [
                chunk.search_text or "",
                chunk.content or "",
                getattr(document, "title", "") or "",
                getattr(document, "source", "") or "",
            ]
        )
        score = score_text(tokens, search_text)
        if score <= 0:
            continue
        ranked.append((score, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1].chunk_index, item[1].id))
    return [chunk for _, chunk in ranked[:limit]]
