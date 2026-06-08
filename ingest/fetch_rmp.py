"""Fetch all RateMyProfessors reviews for the CS1 professors in the guide.

RMP has no official API. The public site is a React app that reads reviews from
a GraphQL endpoint. We hit that endpoint directly:
  - It accepts a fixed `Authorization: Basic dGVzdDp0ZXN0` header (base64 "test:test"),
    which is shared by all clients.
  - It identifies a professor by a base64 "node id" of the form
    base64("Teacher-<numeric id from the /professor/<id> URL>").

For each professor we page through `ratings` using cursor pagination until
`hasNextPage` is false, normalize each review to our schema, and write one JSON
file per professor into documents/rmp/. The raw payloads are saved so the rest
of the pipeline reads local files and never needs to touch RMP again.

Normalized record schema:
    {
        "id":               "rmp-<profid>-<n>",   # stable per professor
        "source":           "rmp",
        "professor":        "Tanvir Ahmed",        # canonical, used for metadata filter
        "course":           "COP3502C",
        "quality_rating":   5,
        "difficulty_rating":4,
        "date":             "2026-05-09 21:00:26 +0000 UTC",
        "text":             "<the review comment>",
    }
"""

import base64
import json
import ssl
import time
import urllib.request
from pathlib import Path

import certifi

# python.org's Python doesn't use the macOS system trust store, so build an SSL
# context from certifi's CA bundle (curl works because it uses the system store).
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"
AUTH_HEADER = "Basic dGVzdDp0ZXN0"  # base64("test:test") — shared public client token
OUT_DIR = Path(__file__).resolve().parent.parent / "documents" / "rmp"
PAGE_SIZE = 20  # RMP caps each request; 20 is the page size the site itself uses

# Canonical professor list. `name` is what we store in metadata and show in the
# dropdown; `rmp_id` is the number from the /professor/<id> URL.
PROFESSORS = [
    {"name": "Tanvir Ahmed",       "rmp_id": "2455124"},
    {"name": "Arup Guha",          "rmp_id": "56125"},
    {"name": "Awrad Ali",          "rmp_id": "3092502"},
    {"name": "Kurt Kullu",         "rmp_id": "2977675"},
    {"name": "Md Mahfuzur Rahaman","rmp_id": "3146605"},
]

RATINGS_QUERY = """
query($id: ID!, $count: Int!, $cursor: String) {
  node(id: $id) {
    ... on Teacher {
      firstName
      lastName
      numRatings
      ratings(first: $count, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            class
            comment
            date
            qualityRating
            difficultyRating
          }
        }
      }
    }
  }
}
"""


def is_cs1(course: str) -> bool:
    """True if the course code is CS1 (COP 3502). RMP course strings are messy
    ('3502C', 'COP3502C', 'COP3223', a 'COP32223' typo, etc.), so we reduce to
    digits and test for the 3502 catalog number."""
    digits = "".join(ch for ch in course if ch.isdigit())
    return "3502" in digits


def node_id(rmp_id: str) -> str:
    """Convert a /professor/<id> URL number into RMP's base64 GraphQL node id."""
    return base64.b64encode(f"Teacher-{rmp_id}".encode()).decode()


def graphql(variables: dict) -> dict:
    """POST the ratings query and return the parsed `data` payload."""
    body = json.dumps({"query": RATINGS_QUERY, "variables": variables}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": AUTH_HEADER,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read())["data"]


def fetch_professor(prof: dict) -> list[dict]:
    """Page through every review for one professor and return normalized records."""
    gid = node_id(prof["rmp_id"])
    records: list[dict] = []
    cursor = None
    while True:
        data = graphql({"id": gid, "count": PAGE_SIZE, "cursor": cursor})
        teacher = data["node"]
        ratings = teacher["ratings"]
        for edge in ratings["edges"]:
            n = edge["node"]
            comment = (n.get("comment") or "").strip()
            if not comment:  # skip ratings with no written review — no text to embed
                continue
            course = (n.get("class") or "").strip()
            records.append(
                {
                    "id": f"rmp-{prof['rmp_id']}-{len(records)}",
                    "source": "rmp",
                    "professor": prof["name"],
                    "course": course,
                    "is_cs1": is_cs1(course),
                    "quality_rating": n.get("qualityRating"),
                    "difficulty_rating": n.get("difficultyRating"),
                    "date": n.get("date"),
                    "text": comment,
                }
            )
        page = ratings["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
        time.sleep(0.5)  # be polite to the endpoint between pages
    return records


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grand_total = 0
    for prof in PROFESSORS:
        records = fetch_professor(prof)
        out_path = OUT_DIR / f"{prof['rmp_id']}.json"
        out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
        grand_total += len(records)
        print(f"{prof['name']:<24} {len(records):>4} reviews with text -> {out_path.name}")
    print(f"\nTotal: {grand_total} reviews saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
