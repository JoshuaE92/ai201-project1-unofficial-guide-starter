"""Milestone 4a — embed every chunk and load it into ChromaDB.

Reads data/chunks.json (output of the ingestion pipeline), embeds each chunk's
text with all-MiniLM-L6-v2 (local, no API key), and stores the vectors in a
persistent ChromaDB collection together with the metadata retrieval needs:
source, source_name (for attribution), position, professor, course, is_cs1, etc.

Why these specific choices:
  * all-MiniLM-L6-v2 — our planning.md model; 384-dim, runs locally, fast.
  * cosine distance — the collection is created with {"hnsw:space": "cosine"} so
    distances land on the familiar 0 (identical) .. 2 (opposite) scale where
    ~0.2 is a strong match and >0.6-0.7 is weak. (Chroma defaults to L2, whose
    scores aren't comparable to the rubric's example numbers.)
  * embeddings are L2-normalized at encode time, which is what cosine expects.

ChromaDB metadata values must be scalar and non-null, so None fields are dropped
per chunk (a Reddit chunk has no `course`; an RMP chunk has no `thread_title`).

Run:  python3 rag/embed_store.py     (rebuilds the collection from scratch)
"""

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_PATH = ROOT / "data" / "chunks.json"
CHROMA_DIR = ROOT / "chroma_db"          # gitignored; rebuildable from chunks.json
COLLECTION = "cs1_reviews"
MODEL_NAME = "all-MiniLM-L6-v2"

# Which chunk fields become Chroma metadata. None values are skipped (Chroma
# rejects nulls). `source_name` and `position` are added in build_metadata.
META_FIELDS = (
    "source", "professor", "course", "is_cs1",
    "quality_rating", "difficulty_rating", "thread_title", "score", "date",
)


def source_name(chunk: dict) -> str:
    """Human-readable 'document' a chunk came from, for later attribution."""
    if chunk["source"] == "rmp":
        return f"RMP — {chunk['professor']}"
    return f"Reddit — {chunk.get('thread_title') or 'thread'}"


def build_metadata(chunk: dict, position: int) -> dict:
    meta = {k: chunk[k] for k in META_FIELDS if chunk.get(k) is not None}
    meta["source_name"] = source_name(chunk)
    meta["position"] = position  # index of this chunk within its source_name group
    return meta


def main() -> None:
    chunks = json.loads(CHUNKS_PATH.read_text())
    print(f"loaded {len(chunks)} chunks from {CHUNKS_PATH.name}")

    print(f"loading embedding model {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)

    texts = [c["text"] for c in chunks]
    print("embedding chunks (this runs locally) ...")
    embeddings = model.encode(
        texts, batch_size=64, normalize_embeddings=True, show_progress_bar=True
    ).tolist()

    # position = running index within each source_name group, for attribution.
    counters: dict[str, int] = {}
    metadatas = []
    for c in chunks:
        sn = source_name(c)
        counters[sn] = counters.get(sn, 0)
        metadatas.append(build_metadata(c, counters[sn]))
        counters[sn] += 1

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    # Rebuild from scratch so re-runs are deterministic.
    if COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    collection = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    # Add in batches (Chroma handles large adds, but batching keeps memory flat).
    B = 256
    for i in range(0, len(chunks), B):
        collection.add(
            ids=[c["id"] for c in chunks[i : i + B]],
            embeddings=embeddings[i : i + B],
            documents=texts[i : i + B],
            metadatas=metadatas[i : i + B],
        )

    print(f"\nstored {collection.count()} chunks in ChromaDB collection '{COLLECTION}'")
    print(f"persisted to {CHROMA_DIR}")


if __name__ == "__main__":
    main()
