# clean_catalog.py
import os
import re
import pandas as pd
from urllib.parse import urlparse
from rule_type_classifier import rule_infer_type   # use your rule-based classifier

# Input file produced by Playwright scraper (full extraction)
IN = "data/catalog_from_excel_full.csv"
OUT = "data/catalog_clean.csv"

os.makedirs("data", exist_ok=True)

# load input (fail with a clear message if missing)
if not os.path.exists(IN):
    raise FileNotFoundError(f"Input CSV not found: {IN}. Run fetch_from_excel_playwright.py first.")

df = pd.read_csv(IN)

def clean(s):
    if pd.isna(s):
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def infer_name(row):
    title = clean(row.get("title", ""))
    if title:
        title = re.sub(r"\s*\|\s*SHL.*$", "", title)
        return title
    url = row.get("canonical_url") or row.get("source_url") or ""
    if not url:
        return "Unknown Assessment"
    part = urlparse(url).path.strip("/").split("/")[-1]
    return part.replace("-", " ").title()

# ---------------------------
# SKILLS + multi-word + synonyms
# ---------------------------

# Canonical skill names we want in output (normalized)
CANONICAL_SKILLS = [
    "sql", "java", "javascript", "python", "react", "aws", "excel",
    "communication", "leadership", "teamwork", "sales", "verbal",
    "numerical", "logical", "management", "customer service",
    "cognitive", "data warehousing", "data entry", "hadoop", "spark",
    "tableau", "power bi", "nlp", "machine learning", "deep learning",
    "devops", "docker", "kubernetes", "microsoft office"
]

# Map synonyms / alternative spellings -> canonical skill
SYNONYMS = {
    # AWS variants
    "aws": "aws",
    "amazon": "aws",
    "amazon web services": "aws",
    "amazon-aws": "aws",
    "amazon aws": "aws",
    "cloud": "aws",   # CAUTION: maps generic 'cloud' -> 'aws' (may be broad)

    # SQL variants
    "ms sql": "sql",
    "mssql": "sql",
    "mysql": "sql",
    "postgres": "sql",
    "postgresql": "sql",

    # Java / JS
    "java script": "javascript",
    "js": "javascript",

    # Excel / Office
    "ms excel": "excel",
    "microsoft excel": "excel",
    "ms office": "microsoft office",

    # Data / BI
    "datawarehouse": "data warehousing",
    "data-warehousing": "data warehousing",
    "data warehouse": "data warehousing",
    "powerbi": "power bi",

    # ML / NLP
    "natural language processing": "nlp",
    "nlp": "nlp",
    "deep-learning": "deep learning",
    "ml": "machine learning",

    # DevOps
    "k8s": "kubernetes",

    # Misc
    "customer-service": "customer service",
    "customerservice": "customer service",
    "call centre": "customer service",
    "call center": "customer service"
}

# Multi-word skills (long phrases first)
MULTI_WORD_SKILLS = [
    "data warehousing",
    "data entry",
    "machine learning",
    "deep learning",
    "customer service",
    "power bi",
    "natural language processing",
    "microsoft office"
]

# Build ordered pattern list:
# 1) multi-word phrases (longest first)
# 2) synonyms (maps to canonical)
# 3) canonical single-word skills (remaining)
_skill_patterns = []

# Add multi-word patterns first (longest-first)
for phrase in sorted(MULTI_WORD_SKILLS, key=lambda x: -len(x)):
    _skill_patterns.append((phrase.lower(), re.compile(rf"\b{re.escape(phrase)}\b", flags=re.I)))

# Add synonyms (maps alternates -> canonical)
for alt, canon in SYNONYMS.items():
    _skill_patterns.append((canon.lower(), re.compile(rf"\b{re.escape(alt)}\b", flags=re.I)))

# Add canonical single-word skills (avoid duplicates)
existing = {k for k, _ in _skill_patterns}
for s in CANONICAL_SKILLS:
    if s.lower() in existing:
        continue
    _skill_patterns.append((s.lower(), re.compile(rf"\b{re.escape(s)}\b", flags=re.I)))

def extract_skills(text):
    """
    Improved skill extractor:
    - matches multi-word phrases first
    - maps synonyms to canonical names
    - uses word-boundary regex to prevent substring false-positives
    - returns sorted, unique comma-separated canonical skill names (lowercase)
    """
    if not text:
        return ""
    t = text.lower()
    found = []
    for canonical, pat in _skill_patterns:
        if pat.search(t):
            found.append(canonical)
    # Deduplicate while preserving order of discovery
    seen = set()
    result = []
    for f in found:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return ",".join(result)

# ---------------------------
# Main cleaning loop
# ---------------------------

out = []

for i, r in df.iterrows():
    name = infer_name(r)

    # prefer extracted_text (full page) then fallback to meta_description / text_snippet / title
    extracted = clean(r.get("extracted_text", ""))
    meta_desc = clean(r.get("meta_description", ""))
    snippet = clean(r.get("text_snippet", ""))
    title = clean(r.get("title", ""))
    url = r.get("canonical_url") or r.get("source_url") or ""

    # Build canonical_text (used for classification & indexing) - NO URLs included here
    if extracted:
        canonical_text = extracted
    else:
        canonical_text = " ".join([title, meta_desc, snippet]).strip()

    # CLASSIFY using full canonical_text
    test_type = rule_infer_type(canonical_text)

    # Build a SAFE skill_text that intentionally EXCLUDES the URL and other boilerplate
    # Use the extracted/meta/snippet/title fields only (no url)
    skill_text = " ".join([title, meta_desc, snippet, extracted]).strip()

    # extract skills from the safe skill_text
    skills = extract_skills(skill_text)

    out.append({
        "assessment_id": f"A{i+1:04d}",
        "assessment_name": name,
        "canonical_url": url,
        "test_type": test_type,
        "skills_tags": skills,
        "canonical_text": canonical_text[:5000]  # store up to 5k chars
    })

pd.DataFrame(out).to_csv(OUT, index=False)
print("Saved cleaned:", OUT)
