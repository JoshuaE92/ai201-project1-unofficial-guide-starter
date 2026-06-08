"""Milestone 4b — retrieval.

retrieve(query, professor=None, is_cs1=None, k=5) embeds the query with the same
all-MiniLM-L6-v2 model and asks ChromaDB for the top-k nearest chunks, optionally
filtering by professor and/or CS1-only first (the metadata filter is exact and
runs before the vector search — that's what keeps one professor's results from
leaking into another's, the core risk in planning.md, Challenge #2).

Returns a list of dicts: {text, distance, source_name, professor, course, ...}.
Lower distance = closer match. With cosine space, ~0.2 is strong, >0.6-0.7 weak.

Run `python3 rag/retrieve.py` to execute the evaluation-plan smoke test below.
"""

from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = ROOT / "chroma_db"
COLLECTION = "cs1_reviews"
MODEL_NAME = "all-MiniLM-L6-v2"

_model = None
_collection = None


def _load():
    """Lazy-load the model and collection once, reuse across queries."""
    global _model, _collection
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = client.get_collection(COLLECTION)
    return _model, _collection


def _build_where(professor, is_cs1):
    conds = []
    if professor:
        conds.append({"professor": professor})
    if is_cs1:
        conds.append({"is_cs1": True})
    if not conds:
        return None
    return conds[0] if len(conds) == 1 else {"$and": conds}


def retrieve(query: str, professor: str = None, is_cs1: bool = False, k: int = 10):
    # k=10 per planning.md (Retrieval Approach): aggregate questions like "best
    # professor" or "who gives extra credit" are answered across many reviews, so
    # a wider top-k feeds generation enough substantive reviews to synthesize from.
    model, collection = _load()
    q_emb = model.encode([query], normalize_embeddings=True).tolist()
    res = collection.query(
        query_embeddings=q_emb,
        n_results=k,
        where=_build_where(professor, is_cs1),
    )
    out = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append({"text": doc, "distance": dist, **meta})
    return out


def _show(query, results, **filters):
    flt = ", ".join(f"{k}={v}" for k, v in filters.items() if v) or "no filter"
    print(f"\n{'='*80}\nQUERY: {query}   [{flt}]")
    for i, r in enumerate(results, 1):
        print(f"\n  #{i}  distance={r['distance']:.3f}   {r['source_name']}"
              f"   (prof={r.get('professor')}, cs1={r.get('is_cs1')})")
        text = r["text"].replace("\n", " ")
        print(f"      {text[:240]}{'…' if len(text) > 240 else ''}")


if __name__ == "__main__":
    # Smoke test against the planning.md evaluation queries (default k=10).
    _show("Which professors give extra credit?",
          retrieve("Which professors give extra credit?"))

    _show("Is Awrad Ali's grading fair or harsh?",
          retrieve("Is the grading fair or harsh?", professor="Awrad Ali"),
          professor="Awrad Ali")

    _show("Overall, who is the best professor for CS1?",
          retrieve("Who is the best professor for CS1?"))

    _show("How hard is Ahmed's class?",
          retrieve("How difficult are the exams and workload?", professor="Tanvir Ahmed"),
          professor="Tanvir Ahmed")
