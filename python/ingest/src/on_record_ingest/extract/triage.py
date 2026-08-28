from __future__ import annotations

import re

REC = re.compile(
    r"\b("
    r"recommend(?:s|ed|ing|ation)?|endorse(?:s|d|ment)?|you should (?:read|try|use|watch|listen(?: to)?|follow|get|buy)|"
    r"check (?:it|this|them|that) out|worth (?:reading|watching|listening to|trying|using|buying)|must[- ](?:read|use|watch|try)|"
    r"(?:i|we) (?:use|used|am using|are using|have been using|have used|rely on|work with|run|wear|take|play|drive)|"
    r"i['’]m using|we['’]re using|(?:i|we)['’]ve been using|personally use|my daily driver|my (?:tech )?stack|our (?:tech )?stack|"
    r"(?:i|we) (?:switched|moved) to|my favou?rite|(?:i|we) (?:really )?(?:love|like|prefer|enjoy|adore)|"
    r"i['’]m (?:a )?(?:(?:big|huge) )?fan of|i am (?:a )?(?:(?:big|huge) )?fan of|i['’]m obsessed with|i swear by|my go[- ]to|"
    r"(?:i|we) (?:read|are reading|am reading|listen to|listened to|watch|watched|subscribe to|subscribed to)|"
    r"i['’]m reading|(?:i|we)['’]ve (?:read|been reading|listened to|watched|subscribed to)|"
    r"(?:i|we) (?:bought|own|have purchased)|(?:i|we)['’]ve (?:bought|purchased)|"
    r"(?:i|we) (?:built|created|made|developed|founded|launched|wrote|authored|designed|shipped|started)|"
    r"don['’]t use|do not use|never use|stop(?:ped)? using|(?:i|we) avoid|switched away from|"
    r"(?:i|we) (?:quit|uninstalled)|stay away from|wouldn['’]t use|would not use|can['’]t use|cannot use"
    r")\b",
    re.IGNORECASE,
)
CLAIM_SIGNALS = {
    "commitment": re.compile(
        r"\b(?:i|we) (?:will|won['’]t|am going to|are going to|plan to|intend to|"
        r"refuse to|commit(?:ted)? to)\b",
        re.IGNORECASE,
    ),
    "evaluation": re.compile(
        r"\b(?:the|this|that|it) (?:is|was|will be) (?:the )?"
        r"(?:best|worst|better|worse|important|critical|essential|valuable|useless|"
        r"dangerous|powerful|wrong|right|mistake|advantage|disadvantage)\b|"
        r"\b(?:doesn['’]t|does not|don['’]t|do not) (?:work|scale|matter|help|solve|replace)\b",
        re.IGNORECASE,
    ),
    "explanation": re.compile(
        r"\b(?:the (?:reason|problem|lesson|key|point|trade[- ]off) is|what matters is|"
        r"because|that means|which means|the way to|the only way)\b",
        re.IGNORECASE,
    ),
    "position": re.compile(
        r"\b(?:i|we) (?:think|believe|argue|expect|predict|prefer|disagree|agree|"
        r"suspect|doubt|would say|would argue|have learned|learned|realized|realised|"
        r"found that|care about)\b|"
        r"\b(?:my|our) (?:view|opinion|belief|take|thesis|experience|prediction)\b|"
        r"\bin my mind\b|\bwill take\b",
        re.IGNORECASE,
    ),
    "uncertainty": re.compile(
        r"\b(?:i|we) (?:don['’]t know|do not know|am not sure|are not sure|might be wrong|"
        r"could be wrong)\b|\bit['’]s unclear\b|\bthere is uncertainty\b",
        re.IGNORECASE,
    ),
}
FILLER = re.compile(
    r"brought to you by|sponsored by|use code |percent off|free trial|"
    r"subscribe to the (?:podcast|channel)|leave (?:us )?a review|we['’]ll be right back|"
    r"thanks for (?:having me|coming on|listening|watching)|"
    r"what is the latest with .{1,100}\bi know you (?:now )?work with|"
    r"we see our customers all the time getting stuck with hacks and workarounds",
    re.IGNORECASE,
)
DETAIL = re.compile(
    r"\b(?:for example|for instance|specifically|in practice|as a result)\b",
    re.IGNORECASE,
)
QUESTION = re.compile(
    r"^(?:what|why|how|when|where|who|which|do|does|did|is|are|was|were|can|could|"
    r"would|should|will|have|has)\b",
    re.IGNORECASE,
)
CONTEXT_DEPENDENT = re.compile(
    r"\b(?:i|we) (?:think|believe|would (?:say|argue)|have found) "
    r"(?:that )?(?:it|they|this|these|those)\b|"
    r"^(?:and|but|so|even if)\b[^.!?]{0,180}\b(?:it|they|them|this|that|these|those)\b",
    re.IGNORECASE,
)

Triage = str  # rec | claim | skip


def claim_excerpt(text: str, max_chars: int = 1200) -> str:
    """A compact exact window around the strongest durable-claim signal."""
    sentences = list(re.finditer(r"[^.!?]+(?:[.!?]+|$)", text))
    if not sentences:
        return text.strip()[:max_chars].strip()
    target = max(
        range(len(sentences)),
        key=lambda index: (
            sum(
                bool(pattern.search(sentences[index].group(0)))
                for pattern in CLAIM_SIGNALS.values()
            )
            * 2
            + (2 if REC.search(sentences[index].group(0)) else 0),
            len(sentences[index].group(0)),
        ),
    )
    target_text = sentences[target].group(0).strip()
    start_index = target
    if target > 0 and (
        len(target_text) < 80
        or re.match(r'^["“”\']?\s*(?:and|but|so|it|they|this|that)\b', target_text, re.IGNORECASE)
    ):
        start_index -= 1
    start = sentences[start_index].start()
    end = sentences[target].end()
    while end - start < 80 and target + 1 < len(sentences):
        target += 1
        end = sentences[target].end()
    if end - start < 40 and start > 0:
        start = sentences[max(0, target - 1)].start()
    return text[start : min(end, start + max_chars)].strip()


def claim_candidate_score(text: str) -> int:
    body = re.sub(r"\s+", " ", text).strip()
    if FILLER.search(body) or (body.endswith("?") and QUESTION.search(body)):
        return 0
    matched = sum(bool(pattern.search(body)) for pattern in CLAIM_SIGNALS.values())
    score = matched * 2 + (2 if REC.search(body) else 0)
    excerpt = claim_excerpt(text)
    if CONTEXT_DEPENDENT.search(excerpt):
        return 0
    if 80 <= len(excerpt) <= 900:
        score += 1
    if excerpt.endswith((".", "!")):
        score += 1
    if DETAIL.search(excerpt):
        score += 1
    if re.match(r"^(?:and|but|so|yeah|well|okay|right)\b", excerpt, re.IGNORECASE):
        score -= 1
    if excerpt.endswith(("-", "…", "...")):
        score -= 2
    return max(score, 0)


def triage_segment(text: str) -> Triage:
    body = re.sub(r"\s+", " ", text).strip()
    if FILLER.search(body):
        return "skip"
    if body.endswith("?") and QUESTION.search(body):
        return "skip"
    score = claim_candidate_score(body)
    if REC.search(body) and score >= 3:
        return "rec"
    if score >= 3:
        return "claim"
    return "skip"
