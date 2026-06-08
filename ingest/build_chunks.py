"""Unify the normalized RMP + Reddit records into the final chunk set.

This is the chunking stage from planning.md. Our strategy is semantic, not
fixed-size: ONE review / ONE comment = ONE chunk, with NO overlap, because each
review is already a self-contained unit of opinion and merging two would blur
their meanings (see planning.md, Chunking Strategy). There is therefore no
chunk_size/overlap parameter to tune — that is intentional for a review corpus,
and the per-chunk length stats printed below confirm chunks land in a healthy
range rather than being fragments or bloated multi-topic blobs.

Two normalization jobs happen here:

1. Cleaning (final pass): every chunk's text is HTML-unescaped and whitespace-
   trimmed so no `&amp;`/`&#39;`/`&nbsp;` or stray markup survives into the
   embedding or the LLM prompt. (Reddit was cleaned at parse time; RMP comments
   are run through the same pass here so cleaning is centralized and uniform.)

2. Professor fan-out: ChromaDB metadata must be scalar, but a Reddit comment can
   mention several professors. A comment tagged with N professors becomes N
   chunks (same text, one scalar `professor` each) so the `where professor == X`
   filter works identically for RMP and Reddit. Comments tagged with no
   professor stay as a single chunk with professor=None (still retrievable for
   un-filtered "general CS1" questions).

Final unified chunk schema (what the Milestone 4 embedder reads):
    {
        "id":               <unique str>,
        "source":           "rmp" | "reddit",
        "professor":        "Tanvir Ahmed" | None,
        "course":           "COP3502C" | None,
        "is_cs1":           bool,
        "quality_rating":   int | None,    # rmp only
        "difficulty_rating":int | None,    # rmp only
        "thread_title":     str | None,    # reddit only
        "score":            int | None,    # reddit only
        "date":             str | None,
        "text":             <cleaned chunk text>,
    }
"""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RMP_DIR = ROOT / "documents" / "rmp"
REDDIT_DIR = ROOT / "documents" / "reddit"
OUT_PATH = ROOT / "data" / "chunks.json"


def clean(text: str) -> str:
    """Final cleaning pass: unescape HTML entities, collapse runs of spaces/tabs,
    trim. Newlines are preserved so the Reddit '[In reply to: ...]' context line
    stays readable."""
    text = html.unescape(text or "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Reviews that carry no opinion at all — pure noise that dilutes similarity
# search. We drop these but KEEP terse-but-real opinions ("unreasonably hard",
# "don't take his classes"), which are legitimate sentiment for a review corpus.
PLACEHOLDERS = {"", "na", "n a", "none", "no comment", "no comments", "."}


def is_substantive(text: str) -> bool:
    norm = re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()
    norm = re.sub(r"\s+", " ", norm)
    return norm not in PLACEHOLDERS


def prof_slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def load_rmp_chunks() -> list[dict]:
    chunks = []
    for path in sorted(RMP_DIR.glob("*.json")):
        for r in json.loads(path.read_text()):
            text = clean(r["text"])
            if not is_substantive(text):
                continue
            chunks.append(
                {
                    "id": r["id"],
                    "source": "rmp",
                    "professor": r["professor"],
                    "course": r["course"] or None,
                    "is_cs1": r["is_cs1"],
                    "quality_rating": r["quality_rating"],
                    "difficulty_rating": r["difficulty_rating"],
                    "thread_title": None,
                    "score": None,
                    "date": r["date"],
                    "text": text,
                }
            )
    return chunks


def load_reddit_chunks() -> list[dict]:
    """One chunk per (comment, professor); comments with no professor stay single."""
    chunks = []
    for path in sorted(REDDIT_DIR.glob("*.json")):
        if path.parent.name == "raw":  # safety; glob won't recurse but be explicit
            continue
        for r in json.loads(path.read_text()):
            text = clean(r["text"])
            if not is_substantive(text):
                continue
            common = {
                "source": "reddit",
                "course": None,
                "is_cs1": False,  # Reddit comments aren't reliably course-scoped
                "quality_rating": None,
                "difficulty_rating": None,
                "thread_title": r["thread_title"],
                "score": r["score"],
                "date": r["date"],
                "text": text,
            }
            profs = r["professors"]
            if profs:
                for name in profs:  # fan out: one scalar professor per chunk
                    chunks.append({"id": f"{r['id']}-{prof_slug(name)}", "professor": name, **common})
            else:
                chunks.append({"id": r["id"], "professor": None, **common})
    return chunks


def print_representative(chunks: list[dict]) -> None:
    """Print 5 chunks chosen to span the range of structures we produce."""
    def first(pred):
        return next((c for c in chunks if pred(c)), None)

    picks = [
        ("RMP / CS1 review",            first(lambda c: c["source"] == "rmp" and c["is_cs1"])),
        ("RMP / non-CS1 review",        first(lambda c: c["source"] == "rmp" and not c["is_cs1"])),
        ("Reddit / names a professor",  first(lambda c: c["source"] == "reddit" and c["professor"] and not c["text"].startswith("[In reply"))),
        ("Reddit / inherited reply",    first(lambda c: c["source"] == "reddit" and c["professor"] and c["text"].startswith("[In reply"))),
        ("Reddit / no professor",       first(lambda c: c["source"] == "reddit" and c["professor"] is None)),
    ]
    print("\n=== 5 representative chunks ===")
    for label, c in picks:
        if not c:
            print(f"\n[{label}] — none found")
            continue
        print(f"\n[{label}]  id={c['id']}")
        print(f"  professor={c['professor']!r}  course={c['course']!r}  is_cs1={c['is_cs1']}  chars={len(c['text'])}")
        print(f"  text: {c['text']}")


def main() -> None:
    # Count raw records first so we can report how many placeholders were dropped.
    raw_rmp = sum(len(json.loads(p.read_text())) for p in RMP_DIR.glob("*.json"))
    raw_reddit_records = [r for p in REDDIT_DIR.glob("*.json") for r in json.loads(p.read_text())]

    chunks = load_rmp_chunks() + load_reddit_chunks()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(chunks, indent=2, ensure_ascii=False))

    lengths = sorted(len(c["text"]) for c in chunks)
    n = len(lengths)
    rmp = sum(1 for c in chunks if c["source"] == "rmp")
    reddit = n - rmp
    no_prof = sum(1 for c in chunks if c["professor"] is None)

    print_representative(chunks)
    print("\n=== chunk stats ===")
    print(f"dropped {raw_rmp - rmp} placeholder RMP reviews (e.g. 'N/A', 'No Comments')")
    print(f"total chunks: {n}   (rmp={rmp}, reddit={reddit}, no-professor={no_prof})")
    print(f"chars  min={lengths[0]}  median={lengths[n // 2]}  max={lengths[-1]}  (~tokens median≈{lengths[n // 2] // 4})")
    print(f"healthy range is 50–2000 chunks -> {'OK' if 50 <= n <= 2000 else 'OUT OF RANGE'}")
    print(f"\nsaved {n} chunks to {OUT_PATH}")


if __name__ == "__main__":
    main()
