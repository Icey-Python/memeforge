"""AI visual-keyword extractor for stock video search.

Turns a finished script into 3-5 concrete *visual* search queries
(e.g. "boiling noodles", "chef cooking pasta", "asian street food
noodle bowl") that the Pexels/Pixabay connectors can look up.

Strategy:
1. Ask the configured LLM connector for JSON queries (`complete_json`
   on the provider; the studio passes its model-node config through).
2. Fall back to a deterministic heuristic (stopword-stripped frequency
   analysis) whenever the LLM is unavailable, unconfigured (mock), or
   returns nothing usable — so the button always works offline.
"""

import re
from collections import Counter
from typing import List

from app.providers.llm.base import BaseLLMProvider

MIN_QUERIES = 3
MAX_QUERIES = 5

# Script generation ships a bigger keyword set alongside the lines so
# the stock montage never needs a second LLM round-trip.
SCRIPT_KEYWORD_MIN = 10
SCRIPT_KEYWORD_MAX = 14

# Stock-search-friendly suffixes used to pad thin keyword sets.
_KEYWORD_SUFFIXES = (
    "close up", "slow motion", "4k", "cinematic", "b-roll", "background",
)

_SYSTEM_PROMPT = (
    "You extract visual stock-video search queries for a short-form "
    "video script. Read the script and output 3-5 concise search "
    "queries (2-4 words each) describing concrete VISUALS that match "
    "the script's content — things a stock video site (Pexels, "
    "Pixabay) would return vertical b-roll footage for. Prefer concrete "
    "subjects and actions over abstract phrases. Respond ONLY with "
    f'JSON: {{"queries": ["...", ...]}} with {MIN_QUERIES}-{MAX_QUERIES} items.'
)

# Common English stopwords — stripped before frequency analysis.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "when",
    "at", "by", "for", "with", "about", "into", "through", "during",
    "before", "after", "to", "from", "up", "down", "in", "out", "on",
    "off", "over", "under", "again", "further", "once", "here", "there",
    "all", "any", "both", "each", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than",
    "too", "very", "can", "will", "just", "should", "now", "this",
    "that", "these", "those", "i", "you", "he", "she", "it", "we",
    "they", "them", "his", "her", "its", "our", "your", "my", "me",
    "him", "us", "what", "which", "who", "whom", "how", "why", "where",
    "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "having", "do", "does", "did", "doing", "would", "could",
    "ought", "of", "as", "because", "while", "until", "get", "got",
    "gonna", "wanna", "one", "two", "three", "really", "actually",
    "literally", "basically", "right", "okay", "yeah", "yes", "also",
}


def heuristic_keywords(
    script: str,
    max_queries: int = MAX_QUERIES,
    min_queries: int = MIN_QUERIES,
    topic: str = "",
) -> List[str]:
    """Deterministic offline extractor: frequency-ranked content words.

    Strips stopwords, ranks the remaining words by frequency, and builds
    short visual queries from the top words (plus stock-y variants when
    the script is too thin for organic multi-word queries). `topic`
    variant phrases (e.g. "elden ring close up") pad the set when the
    script text alone cannot reach `min_queries`.
    """
    words = [w for w in re.findall(r"[a-zA-Z']+", script.lower())]
    content = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    if not content and not topic.strip():
        return []

    counts = Counter(content)
    top = [w for w, _ in counts.most_common(10)]

    queries: List[str] = []
    # Frequent bigrams ("instant ramen", "street food") are the best
    # organic visual queries — collect pairs that occur twice or more.
    bigrams = Counter(zip(content, content[1:]))
    for (a, b), n in bigrams.most_common(6):
        phrase = f"{a} {b}"
        if n >= 2 and phrase not in queries:
            queries.append(phrase)
        if len(queries) >= max_queries - 1:
            break
    # Pad with top single words, then stock-friendly variants.
    for w in top:
        if len(queries) >= max_queries:
            break
        if w not in queries and not any(w in q for q in queries):
            queries.append(w)
    if len(queries) < min_queries:
        # Variant phrases ("{base} close up", "{base} 4k", ...) — topic
        # words first (most on-theme), then the script's top words.
        bases = [w for w in topic.lower().split() if len(w) > 2]
        bases += [w for w in top if w not in bases]
        seen = set(queries)
        for base in bases:
            for suffix in _KEYWORD_SUFFIXES:
                variant = f"{base} {suffix}"
                if len(queries) >= max_queries:
                    break
                if variant not in seen:
                    queries.append(variant)
                    seen.add(variant)
            if len(queries) >= max_queries:
                break
    return queries[:max_queries]


async def extract_visual_keywords(
    script: str, provider: BaseLLMProvider
) -> tuple[List[str], str]:
    """3-5 visual search queries for a script + the source that made them.

    Returns (queries, source) where source is "llm" or "heuristic".
    """
    text = script.strip()
    if not text:
        return [], "heuristic"

    try:
        payload = await provider.complete_json(
            system=_SYSTEM_PROMPT,
            user=f"Script:\n{text}",
        )
        queries = [
            str(q).strip().lower()
            for q in payload.get("queries", [])
            if str(q).strip()
        ]
        # Dedupe while preserving order.
        seen = set()
        queries = [q for q in queries if not (q in seen or seen.add(q))]
        if queries:
            return queries[:MAX_QUERIES], "llm"
    except NotImplementedError:
        pass  # provider (mock) has no LLM behind it — heuristic below
    except Exception:  # noqa: BLE001 - any LLM hiccup falls back offline
        pass

    return heuristic_keywords(text), "heuristic"
