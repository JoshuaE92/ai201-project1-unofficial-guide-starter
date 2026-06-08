# The Unofficial Guide — Project 1

A retrieval-augmented (RAG) question-answering system over real student reviews of
University of Central Florida **Computer Science 1 (COP 3502)** professors. Ask a
question, optionally focus on one professor, and get an answer grounded **only** in
the collected reviews, with the sources it drew from.

**Run it:** `python3 app.py` → open http://localhost:7860

---

## Domain

Student reviews of UCF **CS1 / COP 3502** professors — covering teaching style,
exam and assignment difficulty, grading fairness, and extra-credit policies.

This knowledge is valuable because the decision of *which professor to take for a
weed-out course* heavily affects a student's grade and experience, but it's hard to
find through official channels: the university course catalog lists a generic course
description, not how a specific professor actually teaches, curves exams, or handles
late work. That information lives scattered across RateMyProfessors reviews and Reddit
threads, where it's honest but unstructured, inconsistent, and spread across hundreds
of individual opinions. This system aggregates and makes that informal knowledge queryable.

---

## Document Sources

10 sources: 5 RateMyProfessors professor pages (pulled via RMP's GraphQL endpoint)
and 5 UCF subreddit threads (saved as raw JSON and parsed locally).

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 | RateMyProfessors — Tanvir Ahmed (386 reviews, 233 CS1) | RMP GraphQL → `documents/rmp/2455124.json` | https://www.ratemyprofessors.com/professor/2455124 |
| 2 | RateMyProfessors — Arup Guha (402 reviews, 84 CS1) | RMP GraphQL → `documents/rmp/56125.json` | https://www.ratemyprofessors.com/professor/56125 |
| 3 | RateMyProfessors — Awrad Ali (40 reviews, 18 CS1) | RMP GraphQL → `documents/rmp/3092502.json` | https://www.ratemyprofessors.com/professor/3092502 |
| 4 | RateMyProfessors — Kurt Kullu (85 reviews, 15 CS1) | RMP GraphQL → `documents/rmp/2977675.json` | https://www.ratemyprofessors.com/professor/2977675 |
| 5 | RateMyProfessors — Md Mahfuzur Rahaman (17 reviews, 9 CS1) | RMP GraphQL → `documents/rmp/3146605.json` | https://www.ratemyprofessors.com/professor/3146605 |
| 6 | r/ucf — "CS1 Professor recommendations?" | Reddit JSON → `documents/reddit/raw/cs1_professor_recommendations.json` | https://www.reddit.com/r/ucf/comments/14mqozd/ |
| 7 | r/ucf — "CS1 Professors" | Reddit JSON → `documents/reddit/raw/cs1_professors.json` | https://www.reddit.com/r/ucf/comments/u70c0s/ |
| 8 | r/ucf — "Advice on Professor for Computer Science 1 (Summer)" | Reddit JSON → `documents/reddit/raw/advice_on_professor_for_computer_science_1_summer.json` | https://www.reddit.com/r/ucf/comments/1rgc1e7/ |
| 9 | r/ucf — "CS1 professor next semester" | Reddit JSON → `documents/reddit/raw/cs1_professor_next_semester.json` | https://www.reddit.com/r/ucf/comments/1pblwwm/ |
| 10 | r/ucf — "COP 3502 summer professor" | Reddit JSON → `documents/reddit/raw/json.json` | https://www.reddit.com/r/ucf/comments/1il2o4j/ |

---

## Chunking Strategy

**Chunk size:** Variable — **one review = one chunk** (semantic chunking). No fixed
character/token size. Resulting chunks range from ~5 to ~970 characters (median ≈ 333
chars / ~83 tokens; max ≈ 240 tokens, which stays under the embedding model's 256-token
window so there is effectively no truncation).

**Overlap:** **None.** Each review is already a self-contained unit of opinion. Adding
overlap would bleed one student's review into another's and blur their meanings in the
embedding space, which is the opposite of what we want for a review corpus.

**Why these choices fit your documents:** Every source is review-based. A single review
("his exams are hard but he gives lots of extra credit") is a complete, retrievable
thought — exactly the unit a student's query needs to match. Splitting reviews by a fixed
block length would cut opinions in half; merging several into one chunk would dilute the
embedding so no specific query matches well. Semantic per-review chunking keeps each
embedding focused on one coherent opinion.

**Preprocessing before/at chunking:**
- HTML entities unescaped (`&amp;`, `&#39;` → `&`, `'`) and whitespace collapsed.
- RMP reviews with no written comment, and content-free placeholders (`N/A`,
  `No Comments`), are dropped. Terse-but-real opinions (`unreasonably hard`) are kept.
- **Professor metadata** attached to every chunk (this is the key design choice — see
  Failure Case / Grounded Generation): RMP chunks carry the professor directly; Reddit
  comments are tagged by scanning text against an alias map, with replies that name no
  professor **inheriting** the professor from the nearest naming ancestor comment.
- **Fan-out:** because ChromaDB metadata must be scalar, a Reddit comment that mentions
  two professors becomes two chunks (same text, one professor each) so the filter behaves
  identically for both sources.
- An `is_cs1` flag marks reviews from COP 3502 specifically (RMP reviews span all of a
  professor's courses), so retrieval can optionally restrict to CS1 only.

**Final chunk count:** **962 chunks** (926 RMP + 36 Reddit).

---

## Embedding Model

**Model used:** `all-MiniLM-L6-v2` via `sentence-transformers` (384-dim). It runs locally
with no API key and no rate limits, is fast enough to embed all 962 chunks in seconds,
and is a strong general-purpose semantic model — well suited to short, informal review
text. Distances are computed with **cosine** similarity in ChromaDB. Strong matches land
around 0.18–0.25; aggregate questions sit around 0.45–0.55.

**Production tradeoff reflection:** If I were deploying this for real users and cost were
not a constraint, I'd weigh a few things. **Domain fit:** MiniLM is trained on general
web text, not student slang/grammar ("W professor", "goat", abbreviations), so a model
fine-tuned on informal/educational text could improve recall on noisy reviews. **Context
length:** MiniLM's 256-token window is fine for individual reviews but would truncate long
Reddit comments — a model like `text-embedding-3-large` (8k tokens) would handle longer
context if I switched to bigger chunks. **Latency vs. accuracy:** a hosted API model (e.g.
OpenAI embeddings) is more accurate but adds network latency and per-query cost; for a
live system during fall/spring registration spikes, the local model's zero-latency,
zero-cost profile is actually a real advantage. I'd likely keep a local model for the live
path and reserve a larger API model for offline re-indexing experiments.

---

## Grounded Generation

LLM: **Groq `llama-3.3-70b-versatile`** (free-tier, OpenAI-compatible), temperature 0.1.

**System prompt grounding instruction** (`rag/generate.py`): the model is told it may use
*only* the reviews in the user message, explicitly forbidden from using outside/prior
knowledge, and required to refuse with an exact sentence when the reviews don't cover the
question:

> "You answer questions about UCF Computer Science 1 (COP 3502) professors using ONLY the
> student reviews provided… Do NOT use any outside, general, or prior knowledge… If the
> reviews do not contain enough information to answer, reply with EXACTLY this sentence and
> nothing else: *"I don't have enough information on that."* … Every claim must be supported
> by the reviews… If reviews disagree, say so and summarize both sides. Do not invent
> specifics (grades, policies) not present in the reviews."

This is enforced structurally, not just suggested:
- **Low temperature (0.1)** so the model follows the rules deterministically.
- **Empty-retrieval short-circuit:** if retrieval returns zero chunks (e.g. a professor
  filter with no matching reviews), `ask()` returns the refusal **without calling the LLM
  at all** — it is impossible to hallucinate when there's no evidence.
- Context is passed as a **numbered, professor-attributed block** so the model can ground
  claims in specific reviews.

**How source attribution is surfaced:** Sources are built **programmatically from the
retrieved chunks' metadata** (`source_name`), not from whatever the model writes. The UI
shows them in a separate "Retrieved from" box (e.g. `RMP — Awrad Ali`). If the model issues
the refusal, the source list is emptied so we never attribute a non-answer.

---

## Evaluation Report

Run reproducibly with `python3 -m eval.run_eval`. Filters reflect what a user would
pick in the UI (single-professor questions filter to that professor; comparison/general
questions use no professor filter; "best for CS1" and "general difficulty" use CS1-only).

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | Which professors provide extra credit? | Ahmed, Ali, Rahaman | Names **Ahmed** (cites several reviews); states no extra-credit mention for Guha, Rahaman, or Ali | Partially relevant | **Partially accurate** |
| 2 | Between Ali and Ahmed, whose class seems harder? | Ali | Concludes **Ahmed** is harder; says Ali's reviews don't describe the class as hard | Partially relevant (imbalanced) | **Inaccurate** |
| 3 | Overall, who is the best professor for CS1? | Guha / Ahmed | "No clear consensus"; highlights **Ahmed**, Rahaman, Ali; Guha not surfaced | Relevant | **Partially accurate** |
| 4 | Is Awrad Ali's grading fair or harsh? | Fair | Balanced: several reviews say fair (drops lowest quiz, fair-but-hard exams), several say harsh (AI-use zeros, tight timing). Sources: only Awrad Ali | Relevant | **Accurate** |
| 5 | In general, how difficult are the CS1 professors? | Fair / moderate | Varies: Ahmed/Guha harder, Kullu/Rahaman easier; CS1 rigorous regardless of professor | Relevant | **Accurate** |

**Retrieval quality:** Relevant / Partially relevant / Off-target
**Response accuracy:** Accurate / Partially accurate / Inaccurate

Notes: Q4 and Q5 are strong — grounded, balanced, correctly attributed, and the
professor filter on Q4 returned only Awrad Ali (no leakage). Q1 and Q3 are *grounded but
incomplete*, and Q2 is a genuine miss — both for the same underlying reason, analyzed below.

---

## Failure Case Analysis

**Question that failed:** Q2 — "Between Awrad Ali and Tanvir Ahmed, whose class seems harder?"
(Expected: **Ali**.)

**What the system returned:** It concluded **Tanvir Ahmed's** class is harder, citing
several Ahmed reviews about difficult exams and heavy assignments, and stated that Ali's
reviews "do not mention the class being particularly hard." This contradicts the expected
answer and, more importantly, was reached from a one-sided set of evidence.

**Root cause (tied to a specific pipeline stage):** This is a **retrieval** failure caused
by the interaction of two design facts. (1) The metadata filter is **single-professor**
(the UI dropdown is single-select and the Chroma `where` clause filters one professor), so
a *two-professor comparison* has to run with **no professor filter at all**. (2) The corpus
is heavily **imbalanced** — Ahmed has 233 CS1 reviews while Ali has only 18. With an
unfiltered top-k=10 ranked purely by cosine similarity to "whose class is harder," Ahmed's
large review pool dominates the results: the retrieved set was mostly Ahmed reviews plus a
single Ali review. The model faithfully (correctly, per its grounding) summarized the
evidence it was given — but that evidence was lopsided, so it concluded Ahmed because it
*saw* mostly Ahmed difficulty reviews and almost no Ali ones. Retrieval never gave the LLM
a fair sample of Ali's side.

**What I would change to fix it:** Support **multi-professor retrieval** for comparison
questions — use Chroma's `{"professor": {"$in": [...]}}` filter and retrieve a **balanced
top-k per professor** (e.g. 5 from Ali and 5 from Ahmed) rather than 10 globally. That
guarantees both sides are equally represented regardless of how many total reviews each
professor has. A lighter-weight alternative is to detect a comparison question and run two
separate single-professor retrievals, then merge. Either fix addresses the imbalance at the
retrieval stage, which is where the failure actually originates (the embedding, chunking,
and generation stages all behaved correctly).

---

## Spec Reflection

**One way the spec helped you during implementation:** Writing the **Chunking Strategy**
and **Anticipated Challenges** sections of `planning.md` *before* coding directly produced
the system's most important architectural decision. Challenge #2 ("we won't know which
professor holds which review") forced me to decide up front that professor identity must be
**scalar metadata that retrieval filters on first**, rather than something I'd hope the
embedding would capture. That single up-front decision is exactly what makes the
professor-filtered queries reliable (Q4 returned only Awrad Ali, zero leakage) and is what
turned the abstract "name-blind risk" into a concrete, testable filter I could verify.

**One way your implementation diverged from the spec, and why:** My AI Tool Plan said I'd
collect RMP reviews by **manual capped collection** (hand-copying into a CSV). In
implementation I diverged to an **automated pull from RMP's GraphQL endpoint** instead.
Once I confirmed the endpoint was reachable, it returned every review already structured
with professor, course, rating, and date — far cleaner and more complete (930 reviews) than
hand-copying a capped sample, and fully reproducible. A second, *forced* divergence: I
planned to fetch Reddit threads live with a custom User-Agent, but Reddit hard-blocks
automated `.json` requests (HTTP 403), so I switched to hand-saving each thread's JSON from
the browser and parsing those local files. I also added an `is_cs1` flag that wasn't in the
original spec, after discovering RMP reviews span *all* of a professor's courses, not just CS1.

---

## AI Usage

**Instance 1 — RMP ingestion via GraphQL**

- *What I gave the AI:* My Documents section (the 5 RMP professor URLs) and my normalized
  schema `{id, source, professor, course, rating, date, text}`, and asked for a loader,
  noting I'd planned a manual CSV.
- *What it produced:* It identified that RMP has no public API but serves reviews from a
  hidden GraphQL endpoint, and wrote `fetch_rmp.py` — converting each `/professor/<id>` URL
  into RMP's base64 node id, paging through all reviews with cursor pagination, and
  normalizing them to my schema.
- *What I changed or overrode:* I directed it to **add an `is_cs1` flag** (after we saw RMP
  reviews include Data Structures, AI, intro-to-C, not just CS1), to **normalize messy
  professor name strings** (`"Dr.Awrad"` → canonical `"Awrad Ali"`), and chose to **pull
  all ~930 reviews** rather than cap at N for richer retrieval. I also corrected a duplicate
  professor ID in my own plan (Ahmed and Guha had the same URL).

**Instance 2 — Reddit reply-thread professor tagging**

- *What I gave the AI:* The problem that Reddit replies often discuss a professor without
  naming them (a reply like "his exams are brutal" under a comment about Ahmed), and asked
  how to keep those from being orphaned by the professor filter.
- *What it produced:* A tree-walking parser (`fetch_reddit.py`) that **inherits** professor
  context down the comment tree — a comment's professors are its own detected names, or, if
  it names none, the nearest naming ancestor's — plus a parent-comment snippet prepended to
  each reply so the chunk is self-contained for embedding.
- *What I changed or overrode:* I chose the **"own names win, else inherit"** rule (so a
  reply that switches to a new professor re-tags correctly), and consciously **accepted the
  over-attribution limitation** (a name-less reply under a multi-professor comment inherits
  all of them) rather than over-engineering it. I also decided to **keep terse-but-real
  short reviews** ("unreasonably hard") while dropping only content-free placeholders
  ("N/A", "No Comments").
