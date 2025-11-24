# retrieve_test_no_faiss.py
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
import joblib

META = "data/metadata.csv"
EMB = "data/embeddings.npy"
NN = "data/nn_model.joblib"

df = pd.read_csv(META)
embs = np.load(EMB)
nbrs = joblib.load(NN)
model = SentenceTransformer("all-MiniLM-L6-v2")

def recommend(query, top_k=10):
    qv = model.encode([query], convert_to_numpy=True).astype("float32")
    dists, idxs = nbrs.kneighbors(qv, n_neighbors=min(top_k, len(embs)))

    results = []
    for dist, idx in zip(dists[0], idxs[0]):
        sim = 1 - float(dist)
        row = df.iloc[idx].to_dict()
        row["score"] = sim
        results.append(row)
    return results

if __name__ == "__main__":
    while True:
        q = input("\nQuery: ").strip()
        if q.lower() in ["exit", "quit"]:
            break
        for r in recommend(q, 10):
            print(f"{r['assessment_id']} | {r['assessment_name']} | score={r['score']:.3f}")
