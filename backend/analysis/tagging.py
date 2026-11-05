"""Shared step after reading: tag coach text by topic and pull out venue rules.

Keyword based so it runs offline; swap for an LLM call when the agent gets one.
"""

import re

TOPICS = {
    "Wind": r"\b(wind|breeze|gust|shift|veer|back(?:ing|ed)?|puff|lull|kt|knots?)\b",
    "Current & tide": r"\b(current|tide|flood|ebb|stream)\b",
    "Start": r"\b(start|line bias|pin|committee boat|rc boat|gun)\b",
    "Side of course": r"\b(left|right) (side|hand|paid|pays)\b|\bfavou?red side\b",
    "Upwind / downwind": r"\b(upwind|downwind|beat|run|reach|mark rounding|layline)\b",
    "Boat & setup": r"\b(vang|cunningham|outhaul|rig|mast|sail|setup|kicker)\b",
    "Sailor": r"\b(fatigue|nervous|confiden\w*|focus|hiking|fitness|energy)\b",
}

RULE_CHECKLIST = {
    "Course areas": r"course area|racing area",
    "Exclusion zones": r"exclusion|prohibited|restricted|shipping (lane|channel)|keep clear",
    "Start sequence": r"warning signal|preparatory|start(ing)? sequence|\b[45]\s*-?minute",
    "Time limits": r"time limit|finishing window|target time",
    "Communication": r"\bvhf\b|channel \d+|radio",
    "Penalties & protests": r"penalt|protest|scoring",
    "Safety": r"safety|life ?jacket|pfd|check[- ]?(in|out)",
}
_RULE_WORDS = re.compile(r"\b(must|shall|shall not|may not|not permitted|prohibited|required|"
                         r"exclusion|time limit|signal|penalt|protest)\b", re.I)


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [part.strip(" -•\t") for part in parts if len(part.strip()) > 3]


def tag(text):
    """{topic: [sentences mentioning it]} for every topic that appears."""
    found = {}
    for sentence in sentences(text):
        for topic, pattern in TOPICS.items():
            if re.search(pattern, sentence, re.I):
                found.setdefault(topic, []).append(sentence)
    return found


def extract_rules(text):
    """Sentences that read like rules, plus which checklist items they cover."""
    rules = [s for s in sentences(text) if _RULE_WORDS.search(s)]
    covered = {item: [s for s in sentences(text) if re.search(pattern, s, re.I)]
               for item, pattern in RULE_CHECKLIST.items()}
    return rules, covered
