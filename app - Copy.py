import pandas as pd
import numpy as np
import joblib
from sentence_transformers import SentenceTransformer
import math
import traceback
import sys
import re
import os
from flask import Flask, request, jsonify, render_template, send_from_directory

# --- App Setup ---
app = Flask(__name__)

# --- Constants ---
META = "data/metadata.csv"
EMB = "data/embeddings.npy"
NN = "data/nn_model.joblib"

# --- Load Models at Startup ---
try:
    # Check that the data files exist (they should be downloaded by the build command)
    if not os.path.exists(META):
        print(f"ERROR: Model file not found at {META}. Deployment build step may have failed.", file=sys.stderr)
        sys.exit(1)
    
    df = pd.read_csv(META)
    embs = np.load(EMB)
    nbrs = joblib.load(NN)
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("API: Loaded metadata, embeddings, NN and model.")
except Exception:
    print("API startup error:", file=sys.stderr)
    traceback.print_exc()
    raise

# --- Helper Functions (from original api.py) ---

def boost_by_text_match(results, query, boost=0.25):
    """
    Boost items whose canonical_text contains query tokens (or multi-word phrases).
    """
    if not query:
        return results
    q = query.lower()
    multi_phrases = [
        "power bi", "data warehousing", "machine learning", "deep learning",
        "amazon web services", "amazon aws"
    ]
    desired = set()
    for p in multi_phrases:
        if p in q:
            desired.add(p)
    tokens = [t for t in re.split(r'\W+', q) if len(t) > 1]
    for t in tokens:
        desired.add(t)

    for r in results:
        base = float(r.get("score", 0.0))
        canon = (r.get("canonical_text") or "").lower()
        matches = 0
        for d in desired:
            if d in canon:
                matches += 1
        r["score"] = base + matches * boost
        r["_text_match_count"] = matches
    results.sort(key=lambda x: x["score"], reverse=True)
    return results

def safe_float(x, default=0.0):
    """Return finite float or default if NaN/inf/None."""
    try:
        if x is None:
            return float(default)
        f = float(x)
        if not math.isfinite(f):
            return float(default)
        return f
    except Exception:
        return float(default)

# --- Flask Routes ---

@app.route("/")
def index():
    """Serves the main HTML page."""
    return render_template("index.html")

@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"ok": True})

@app.route("/recommend", methods=["POST"])
def recommend():
    """Main recommendation API endpoint."""
    try:
        data = request.json
        q = (data.get("query") or "").strip()
        k = int(data.get("top_k", 10))
        if k <= 0: k = 10


        # encode query
        qv = model.encode([q], convert_to_numpy=True).astype("float32")

        # choose neighbors
        n_neighbors = min(max(k, 10), len(embs))
        dists, idxs = nbrs.kneighbors(qv, n_neighbors=n_neighbors)

        out = []
        for dist, idx in zip(dists[0].tolist(), idxs[0].tolist()):
            if idx is None or idx < 0 or idx >= len(df):
                continue
            row = df.iloc[int(idx)].to_dict()
            score = safe_float(1.0 - dist, default=0.0)

            # sanitize
            aid = str(row.get("assessment_id", "")) if row.get("assessment_id") is not None else ""
            aname = str(row.get("assessment_name", "")) if row.get("assessment_name") is not None else ""
            curl = str(row.get("canonical_url", "")) if row.get("canonical_url") is not None else ""
            ttype = str(row.get("test_type", "")) if row.get("test_type") is not None else ""
            skills = str(row.get("skills_tags", "")) if row.get("skills_tags") is not None else ""
            canonical = str(row.get("canonical_text", "")) if row.get("canonical_text") is not None else ""

            if not math.isfinite(score) or abs(score) > 1e6:
                score = 0.0

            out.append({
                "assessment_id": aid,
                "assessment_name": aname,
                "canonical_url": curl,
                "test_type": ttype,
                "skills_tags": skills,
                "canonical_text": canonical,   # for reranking
                "score": float(score)
            })

        # Apply text-match boosting
        out = boost_by_text_match(out, q, boost=0.25)

        # Prepare final output
        final = []
        for r in out[:k]:
            item = {
                "assessment_id": r.get("assessment_id", ""),
                "assessment_name": r.get("assessment_name", ""),
                "canonical_url": r.get("canonical_url", ""),
                "test_type": r.get("test_type", ""),
                "skills_tags": r.get("skills_tags", ""),
                "score": float(r.get("score", 0.0))
            }
            final.append(item)

        return jsonify({"query": q, "recommendations": final})

    except Exception as e:
        print("Exception in /recommend:", file=sys.stderr)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- Static File Route (for CSS/JS) ---
# Flask's `render_template` and `url_for` handle this automatically
# when files are in `static` and `templates` folders.
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)


# --- Run Server ---
if __name__ == "__main__":
    # Get port from environment variable or default to 8000
    port = int(os.environ.get("PORT", 8000))
    # Run on 0.0.0.0 to be accessible externally (like on Render)
    app.run(host="0.0.0.0", port=port)