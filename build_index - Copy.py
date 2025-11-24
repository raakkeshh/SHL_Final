# build_index_no_faiss.py
import os
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors
import joblib

IN = "data/catalog_clean.csv"
EMB = "data/embeddings.npy"
META = "data/metadata.csv"
NN = "data/nn_model.joblib"

os.makedirs("data", exist_ok=True)

df = pd.read_csv(IN)
texts = df["canonical_text"].fillna("").tolist()

print("Loading model...")
model = SentenceTransformer("all-MiniLM-L6-v2")

print("Encoding...")
embs = model.encode(texts, show_progress_bar=True, batch_size=16)
embs = np.asarray(embs, dtype="float32")

np.save(EMB, embs)
df.to_csv(META, index=False)

print("Building sklearn NN...")
n_neighbors = min(50, len(embs))
nbrs = NearestNeighbors(n_neighbors=n_neighbors, metric="cosine").fit(embs)
joblib.dump(nbrs, NN)

print("Done. Saved embeddings + NN model.")
