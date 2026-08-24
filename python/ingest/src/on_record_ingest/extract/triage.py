from __future__ import annotations

import re

REC = re.compile(
    r"\b("
    r"recommend(?:s|ed|ing)?|i use|i used|i've been using|personally use|"
    r"favorite (?:book|app|tool)|reading list|i read|worth reading|"
    r"i built|don't use|stop using|switched to"
    r")\b",
    re.IGNORECASE,
)
CLAIM = re.compile(
    r"\b("
    r"i think|i believe|in my mind|my view|my reaction|"
    r"will take|predict|bottleneck|over-prediction|the problem is"
    r")\b",
    re.IGNORECASE,
)
NAMED = re.compile(
    r"\b("
    r"claude|codex|cursor|chatgpt|nanochat|gemini|anthropic|openai|"
    r"notion|obsidian|kindle|stripe|tesla"
    r")\b",
    re.IGNORECASE,
)
FILLER = re.compile(
    r"thanks for (having me|coming on)|sponsored by|use code |"
    r"subscribe to|we'll be right back|thanks for watching",
    re.IGNORECASE,
)

Triage = str  # rec | claim | skip


def triage_segment(text: str) -> Triage:
    body = text.strip()
    rec = bool(REC.search(body) or NAMED.search(body))
    if rec:
        return "rec"
    if len(body) < 80:
        return "skip"
    claim = bool(CLAIM.search(body))
    if FILLER.search(body) and not claim:
        return "skip"
    if claim:
        return "claim"
    return "skip"
