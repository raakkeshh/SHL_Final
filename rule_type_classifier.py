# rule_type_classifier.py
import re

TYPE_KEYWORDS = {
    "A": [
        "ability", "aptitude", "cognitive", "reasoning",
        "numerical", "verbal ability", "verbal", "logic", "logical"
    ],
    "B": [
        "biodata", "situational judgement", "sjt",
        "scenario based", "what would you do"
    ],
    "C": [
        "competency", "competencies", "competency framework", "ucf"
    ],
    "D": [
        "360", "leadership development", "development report",
        "feedback report", "development center", "assessment center"
    ],
    "E": [
        "assessment exercise", "exercise", "assessment exercises"
    ],
    "K": [
        "skill", "skills", "technical", "coding", "programming",
        "knowledge", "sql", "java", "python", "it skills"
    ],
    "P": [
        "personality", "motivational", "behaviour", "behavior",
        "leadership style", "opq", "mq", "team types",
        "interpersonal", "communication", "traits", "psychometric"
    ],
    "S": [
        "simulation", "simulations", "call center simulation",
        "job simulation", "scenario simulation"
    ],
    "V": [
        "video interview", "smart interview", "recorded interview",
        "video feedback"
    ]
}

# Precompile regex patterns for speed
TYPE_PATTERNS = {
    t: [re.compile(r"\b" + re.escape(k) + r"\b", flags=re.I) for k in kws]
    for t, kws in TYPE_KEYWORDS.items()
}

# Priority for breaking ties when multiple types score the same
PRIORITY = ["K", "P", "A", "S", "V", "D", "C", "E", "B"]

def rule_infer_type(text: str) -> str:
    text = (text or "").lower()
    scores = {t: 0 for t in TYPE_PATTERNS.keys()}
    for t, patterns in TYPE_PATTERNS.items():
        for p in patterns:
            if p.search(text):
                scores[t] += 1
    best_score = max(scores.values())
    if best_score == 0:
        return "K"  # default fallback
    candidates = [t for t, v in scores.items() if v == best_score]
    for p in PRIORITY:
        if p in candidates:
            return p
    return candidates[0]
