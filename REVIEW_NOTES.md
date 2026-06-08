# 🔖 Review Notes — come back to these (for Josh)

This is your personal "I built it at 3am, now let me actually understand and
test it" doc. Nothing here is required for submission — it's a map of what to
revisit, what each piece does, and **commands you can run yourself** to check
the work. Each section is independent; skim the headers and jump to what you want.

Run everything from the project root:
`/Users/joshuaestime/Projects/CodePath/AI/Project1/ai201-project1-unofficial-guide-starter`

---

## ⭐ 1. Chunk inspection — "are my chunks good?" (the one you asked about)

**What "a good chunk" means:** one chunk = one complete, standalone thought.
If you read a chunk by itself, could you answer a question from it without
needing the text before or after it?

- ✅ Good: `"Ahmed gives lots of extra credit but his exams are hard and based on lecture."`
- ❌ Too small (fragment): `"Ahmed gives lots of"`
- ❌ Too big (many topics mashed): a 600-word blob covering teaching + parking + advising
- ❌ Not cleaned: `"Ahmed&#39;s exams are <div>hard</div>"`

**The file to inspect:** `data/chunks.json` — this is the final output, a list of
chunk objects. Each looks like:
```json
{ "id": "...", "source": "rmp", "professor": "Tanvir Ahmed",
  "course": "COP3502C", "is_cs1": true, "text": "the review..." }
```

### How I inspected them (run these yourself)

**a) Rebuild the chunks and see the summary** (this prints 5 sample chunks + stats):
```bash
python3 ingest/build_chunks.py
```
Look at the bottom: `total chunks`, and `chars min/median/max`. Rule of thumb
from the checkpoint: **between 50 and 2000 chunks** is healthy. We have 962. ✅

**b) Read random chunks yourself and judge them** (change the number to see more):
```bash
python3 -c "
import json, random
c = json.load(open('data/chunks.json'))
for x in random.sample(c, 8):
    print(f\"--- [{x['source']}] {x['professor']} | {len(x['text'])} chars ---\")
    print(x['text']); print()
"
```
For each one ask: *complete thought? standalone? on-topic (about a CS prof)?*

**c) Hunt for problems — short fragments and leftover HTML:**
```bash
python3 -c "
import json, re
c = json.load(open('data/chunks.json'))
print('shortest 10 chunks:')
for x in sorted(c, key=lambda x: len(x['text']))[:10]:
    print(f\"  {len(x['text']):>3}  {x['text']!r}\")
print('chunks still containing HTML entities:',
      sum(1 for x in c if re.search(r'&(amp|lt|gt|nbsp|#39|quot);', x['text'])))
"
```
Currently: 0 HTML entities, shortest is `'Great'` (a real, if tiny, opinion).

### 🟡 Decision left open for you
The shortest chunks (`'Great'`, `'unreasonably hard'`) are terse but real
opinions, so I **kept** them. If when you test retrieval they feel like noise,
tighten the filter in `ingest/build_chunks.py` → `is_substantive()` (e.g. require
`len(text) >= 15`) and re-run. **Try it both ways and see which gives better answers.**

---

## 2. The `is_cs1` flag — test which corpus answers better

Every chunk has `is_cs1` (true if the course is COP 3502). RMP reviews span ALL
a professor's courses, not just CS1. We kept everything + flagged, so later you
can retrieve from **all reviews** or **CS1-only** and compare answer quality.
Counts: 359 CS1 reviews out of 930. **Revisit when evaluating** — does filtering
to CS1 give sharper answers, or do you lose too much data (Rahaman has only 9 CS1)?

```bash
python3 -c "
import json,glob
c=[r for f in glob.glob('documents/rmp/*.json') for r in json.load(open(f))]
print('CS1:', sum(r['is_cs1'] for r in c), '/ total:', len(c))
"
```

---

## 3. Concepts to actually understand later (we talked through these)

- **Why embeddings DON'T track professor names.** Embeddings capture *meaning/topic*,
  not *who*. So "is Ahmed's grading fair?" would match grading-fairness reviews for
  ANY prof. That's why we store the professor as **metadata** and filter on it
  (exact match) BEFORE the similarity search. Two jobs: metadata = "whose?",
  embedding = "about what?".
- **Why we clean text.** MiniLM has a ~256-token window; junk (HTML, boilerplate)
  wastes it and blurs the meaning vector. Clean text → sharper retrieval + cleaner
  evidence for the LLM.
- **Professor fan-out (Reddit).** ChromaDB metadata must be a single value, not a
  list. A Reddit comment naming 2 profs becomes 2 chunks (same text, one prof each)
  so the filter works the same as RMP.
- **Reddit tree inheritance (Challenge #2).** A reply that names no prof inherits
  the professor from its parent comment. Known weakness: if the parent compared
  several profs, the reply inherits all of them (over-attribution). See planning.md.

Ask me to walk through any of these line-by-line when you're fresh.

---

## 4. What's built vs. what's next

**Built (Milestone 3 — ingestion + chunking):**
- `ingest/fetch_rmp.py` — pulls all RMP reviews via GraphQL → `documents/rmp/*.json`
- `ingest/fetch_reddit.py` — parses hand-saved Reddit threads → `documents/reddit/*.json`
- `ingest/build_chunks.py` — cleans + unifies everything → `data/chunks.json` (962 chunks)

**Next (Milestone 4 — embedding + retrieval):**
- Embed each chunk with `all-MiniLM-L6-v2`, store in ChromaDB with metadata
- `retrieve(query, professor, k)` — filter by professor first, then vector search
- Test the name-blind risk: query one prof, confirm no other prof's reviews come back

**After (Milestone 5 — generation + interface):**
- `build_prompt()` + Groq `llama-3.3-70b-versatile` call + Streamlit/CLI front end
- Run the 5 eval questions from planning.md

---

## 5. Things to double-check before submitting
- [ ] Re-read 8–10 random chunks and confirm they're standalone (section 1b)
- [ ] Decide the short-chunk filter (keep vs. `len >= 15`) after testing retrieval
- [ ] Decide all-reviews vs. CS1-only after testing retrieval (section 2)
- [ ] Make sure I can explain the fan-out + inheritance in my own words (section 3)
- [ ] Fill in the README.md sections (Domain, Sources, Chunking) — mirror planning.md
