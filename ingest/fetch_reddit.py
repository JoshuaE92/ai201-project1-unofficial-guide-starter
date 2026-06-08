"""Parse locally-saved UCF CS1 Reddit threads and normalize them.

Reddit hard-blocks automated `.json` fetches (bot detection, regardless of
User-Agent), so the raw threads are saved by hand from a browser into
documents/reddit/raw/ — one file per thread. Each file is Reddit's standard
2-element payload: [0] is the post, [1] is the comment tree (each comment
carries its own nested `replies`). We walk that tree and turn each comment into
one normalized record, solving the two problems unique to threaded discussion
(see planning.md, Challenge #2):

1. Orphaned replies — a reply like "yeah his exams are brutal" never names the
   professor it's about. We carry professor context DOWN the tree: a comment's
   professors are its own detected names, or, if it names none, the nearest
   naming ancestor's. (Own names win, so "nah take Guha instead" retags cleanly.)

2. Contextless reply text — that same reply is a weak embedding and weak evidence
   on its own. We prepend a short snippet of the parent comment so the chunk is
   self-contained for both the embedding model and the LLM.

Professor detection uses a curated alias map with word-boundary matching. "Ali"
is deliberately excluded (too common a word); we require "awrad" / "dr ali".

Normalized record schema:
    {
        "id":           "reddit-<thread>-<comment>",
        "source":       "reddit",
        "professors":   ["Tanvir Ahmed", ...],   # may be empty; list, unlike RMP's scalar
        "thread_id":    "14mqozd",
        "thread_title": "CS1 professor recommendations",
        "score":        12,
        "depth":        1,
        "date":         "2023-06-29 ...",         # ISO from created_utc
        "text":         "[In reply to: \"...\"]\n<cleaned comment body>",
    }

`professors` is stored as a list here because that's faithful to the raw data.
ChromaDB metadata must be scalar, so the fan-out to one-record-per-professor is
handled later in build_chunks (Milestone 4), not baked into raw ingestion.
"""

import datetime as dt
import html
import json
import re
from pathlib import Path

REDDIT_DIR = Path(__file__).resolve().parent.parent / "documents" / "reddit"
RAW_DIR = REDDIT_DIR / "raw"          # hand-saved Reddit .json payloads (input)
OUT_DIR = REDDIT_DIR                  # normalized <thread_id>.json (output)
PARENT_SNIPPET_CHARS = 140            # how much parent text to carry into a reply chunk

# Canonical name -> accepted spellings. Matched case-insensitively on word
# boundaries. "Ali" alone is omitted on purpose (matches too much); we require
# "awrad" or a titled "dr ali".
PROFESSOR_ALIASES = {
    "Tanvir Ahmed":        ["ahmed", "tanvir"],
    "Arup Guha":           ["guha", "arup"],
    "Awrad Ali":           ["awrad", "dr ali", "dr. ali", "professor ali"],
    "Kurt Kullu":          ["kullu", "kurt"],
    "Md Mahfuzur Rahaman": ["rahaman", "mahfuzur"],
}

# Precompile one word-boundary regex per professor (escaped, OR-joined aliases).
ALIAS_PATTERNS = {
    name: re.compile(r"\b(" + "|".join(re.escape(a) for a in aliases) + r")\b", re.IGNORECASE)
    for name, aliases in PROFESSOR_ALIASES.items()
}


def clean_text(body: str) -> str:
    """Unescape HTML entities and collapse whitespace. Returns '' for non-content."""
    if not body or body in ("[deleted]", "[removed]"):
        return ""
    text = html.unescape(body)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_professors(text: str) -> list[str]:
    """Return canonical names whose aliases appear in `text` (word-boundary match)."""
    return [name for name, pat in ALIAS_PATTERNS.items() if pat.search(text)]


def iso_date(created_utc) -> str | None:
    if created_utc is None:
        return None
    return dt.datetime.fromtimestamp(created_utc, tz=dt.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S %z"
    )


def walk_comments(children, thread, inherited, parent_text, records):
    """Recursively walk the comment forest, depth-first.

    inherited:   professors resolved from the nearest naming ancestor
    parent_text: cleaned body of the immediate parent comment (or "" at top level)
    """
    for child in children:
        if child.get("kind") != "t1":  # skip "more" (collapsed) and non-comments
            continue
        data = child["data"]
        body = clean_text(data.get("body", ""))
        if not body:
            continue

        # Resolve professors: own names win; otherwise inherit from ancestor.
        own = detect_professors(body)
        resolved = own if own else inherited

        # Build self-contained chunk text: prepend a parent snippet for replies.
        if parent_text:
            snippet = parent_text[:PARENT_SNIPPET_CHARS].rstrip()
            if len(parent_text) > PARENT_SNIPPET_CHARS:
                snippet += "…"
            chunk_text = f'[In reply to: "{snippet}"]\n{body}'
        else:
            chunk_text = body

        records.append(
            {
                "id": f"reddit-{thread['id']}-{data.get('id')}",
                "source": "reddit",
                "professors": resolved,
                "thread_id": thread["id"],
                "thread_title": thread["title"],
                "score": data.get("score"),
                "depth": data.get("depth", 0),
                "date": iso_date(data.get("created_utc")),
                "text": chunk_text,
            }
        )

        # Recurse into replies, passing this comment's resolved professors + body down.
        replies = data.get("replies")
        if isinstance(replies, dict):
            walk_comments(
                replies["data"]["children"], thread, resolved, body, records
            )


def parse_thread(payload: list) -> list[dict]:
    """Turn one raw Reddit .json payload into normalized comment records."""
    post = payload[0]["data"]["children"][0]["data"]
    thread = {"id": post["id"], "title": post["title"]}
    records: list[dict] = []
    walk_comments(payload[1]["data"]["children"], thread, [], "", records)
    return records


def main() -> None:
    raw_files = sorted(RAW_DIR.glob("*.json"))
    if not raw_files:
        raise SystemExit(f"No raw threads found in {RAW_DIR} — save Reddit .json files there first.")
    grand_total = 0
    for raw_path in raw_files:
        payload = json.loads(raw_path.read_text())
        records = parse_thread(payload)
        thread_id = records[0]["thread_id"]
        out_path = OUT_DIR / f"{thread_id}.json"
        out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
        tagged = sum(1 for r in records if r["professors"])
        title = records[0]["thread_title"]
        print(f"{thread_id:<10} {len(records):>3} comments ({tagged:>3} prof-tagged)  {title[:50]}")
        grand_total += len(records)
    print(f"\nTotal: {grand_total} comments saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
