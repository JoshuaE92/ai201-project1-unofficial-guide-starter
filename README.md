# The Unofficial Guide — Project 1

A retrieval-augmented (RAG) question-answering system over real student reviews of
University of Central Florida **Computer Science 1 (COP 3502)** professors. Ask a
question, optionally focus on one professor, and get an answer grounded **only** in
the collected reviews, with the sources it drew from.

**Repository:** https://github.com/JoshuaE92/ai201-project1-unofficial-guide-starter

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

## Sample Chunks

Five representative chunks, each labeled with its source document. They span both
sources and both Reddit chunk types (a comment that names a professor, and a reply
that inherited its professor via the tree walk and carries a parent-context line).

**Chunk 1 — source: RMP — Tanvir Ahmed** (`rmp-2455124-0`, is_cs1=True)
> Might not be the best idea to take this prof if you're not a CS major. Lectures are
> hard to follow/sit through, very large programming assignments every 2 weeks. The
> course feels like it is built with the assumption that the students are already
> proficient at C and writing algorithms. Had to self-teach a lot. Lots of extra credit
> opportunities tho

**Chunk 2 — source: RMP — Awrad Ali** (`rmp-3092502-0`, is_cs1=False)
> For an intro course, this class was very difficult. The difficulty ramps up very
> quickly. Most of the prerecorded lectures are reused from previous years. Tests are
> fairly challenging requiring a solid grasp on the material. Dr. Ali is helpful during
> office hours and tries her best to help her students. Avoid taking online if possible!

**Chunk 3 — source: RMP — Arup Guha** (`rmp-56125-2`, is_cs1=True)
> I took his CS1 class as a CS minor, Mechanical Engineering major. Guha does a great job
> at making you think hard in every problem, doesn't make anything easy, but doesn't throw
> any major curveballs either. Use his online notes and office hours and really make an
> effort to do the programming assignments, and he'll be the best teacher you can have.

**Chunk 4 — source: Reddit — "CS1 Professor recommendations?"** (`reddit-14mqozd-jq3e495-tanvir_ahmed`)
> Meade is a nightmare according to some students. Ahmed is very passionate about teaching
> the material, he does have an accent but it's nothing bad. Guha can be tough but if you
> pay attention, it can be very beneficial when it comes to taking the foundation exam
> considering he's one of the professor who makes the exam…

**Chunk 5 — source: Reddit — "CS1 Professor recommendations?"** (`reddit-14mqozd-jqbluj9`, inherited reply)
> [In reply to: "Gerber is the best professor"]
> Me sitting here seeing people suffer when I took CS1 with Gerber over summer before he
> stopped teaching it. Thinking about how his extra credit, resubmissions, take home exams,
> and individual student grade scaling… allowed me to pass the class…

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

## Retrieval Test Results

Three queries with their top-3 retrieved chunks and cosine distances (lower = closer).
Reproduce with `python3 rag/retrieve.py`.

**Query A — "Who is the best professor for CS1?"** (no professor filter)
| dist | source | chunk (truncated) |
|------|--------|-------------------|
| 0.180 | RMP — Tanvir Ahmed | "Awesome professor for CS1!" |
| 0.201 | RMP — Md Mahfuzur Rahaman | "Absolutely the best professor that teaches CS1… Gave us so many opportunities for extra credit…" |
| 0.206 | RMP — Tanvir Ahmed | "Good professor overall. CS1 is a lot of work don't slack off. He gives really good lectures…" |

*Why these are relevant:* every result is an explicit, positive judgment about a
professor **for CS1 specifically**, which is exactly what the query asks. The top
distance (0.180) is very low because "Awesome professor for CS1!" is almost a paraphrase
of the query in meaning. Note the match is **semantic, not keyword**: the query never
says "awesome" or "best teaches," yet those reviews rank highest because their *meaning*
is closest. The results also correctly surface the two professors most praised in the
corpus (Ahmed, Rahaman).

**Query B — "How hard are the exams and workload?"** (professor = Tanvir Ahmed)
| dist | source | chunk (truncated) |
|------|--------|-------------------|
| 0.435 | RMP — Tanvir Ahmed | "Very difficult exams and quizzes. I did very good in python… but didn't pass a single exam…" |
| 0.438 | RMP — Tanvir Ahmed | "While the class material itself is pretty difficult, Dr. Ahmed makes it easy to understand…" |
| 0.463 | RMP — Tanvir Ahmed | "Exams are mid-hard but there're extra credits and lots of points in other assignments…" |

*Why these are relevant:* the professor filter ran first, so **all three results are
Tanvir Ahmed** (no other professor leaks in — the core Challenge #2 guarantee). Within
that filter, every chunk is specifically about exam/quiz/assignment difficulty and
workload — the exact aspect queried. Distances are higher than Query A (~0.44) because the
query is an aspect question rather than a near-paraphrase, but the content is on-target.

**Query C — "Does this professor give extra credit?"** (professor = Md Mahfuzur Rahaman)
| dist | source | chunk (truncated) |
|------|--------|-------------------|
| 0.499 | RMP — Md Mahfuzur Rahaman | "Overall a solid professor. He was able to explain topics well and was fair with exam material." |
| 0.516 | RMP — Md Mahfuzur Rahaman | "Really nice professor, the material is hard but if you do the exercise pdfs…" |
| 0.528 | RMP — Md Mahfuzur Rahaman | "I think he is a good professor… This class is just brutally difficult…" |

(All correctly filtered to Rahaman, but distances are moderate-to-weak and the top chunks
don't actually mention extra credit — Rahaman's one explicit extra-credit review didn't
rank in the top 3 here. This previews the recall issue discussed in the Failure Case.)

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

## Example Responses

Each response below is shown exactly as the system returns it: the generated **Answer**
plus the **Retrieved from** source list (the system's programmatic attribution).

**Example 1 — "Which professors give extra credit?"** (no professor filter)
> **Answer:** According to the reviews, Professor Tanvir Ahmed provides extra credit. This
> is mentioned in reviews [1], [2], [6], and [9], which all state that he offers numerous
> extra credit opportunities to help his students succeed. There is no mention of extra
> credit in the reviews for Professors Arup Guha, Md Mahfuzur Rahaman, or Awrad Ali.
>
> **Retrieved from:**
> • RMP — Tanvir Ahmed · • RMP — Arup Guha · • RMP — Md Mahfuzur Rahaman · • RMP — Awrad Ali

**Example 2 — "Is the grading fair or harsh?"** (professor = Awrad Ali)
> **Answer:** The reviews disagree on whether the grading is considered fair or harsh. Some
> students (reviews [3], [5], [8], [10]) consider it fair — [3] notes the lowest quiz grade
> is dropped, [5] says homework and exams were hard but fair. Others (reviews [1], [2], [7],
> [9]) consider it harsh — [1] and [9] mention zeros for suspected AI use, [2] says asking a
> peer for help resulted in a 50% grade, [7] found exams poorly organized.
>
> **Retrieved from:**
> • RMP — Awrad Ali

**Example 3 — out-of-scope query (refusal):** "What do students say about the parking garage by the engineering building?"
> **Answer:** I don't have enough information on that.
>
> **Retrieved from:** (no sources — question not covered by the reviews)

The system declines rather than answering from general knowledge, even though a large
language model "knows" plenty about parking generally — because the prompt forbids outside
knowledge and the retrieved reviews don't cover the topic.

---

## Query Interface

A **Gradio** web UI (`app.py`), launched with `python3 app.py` at http://localhost:7860.

**Input fields:**
- **Professor** (dropdown) — "All professors" (default) or one of the five professors.
  Selecting one applies the metadata filter so the answer draws only from that professor.
- **CS1 (COP 3502) reviews only** (checkbox) — restricts retrieval to reviews flagged
  `is_cs1`, excluding the professor's other courses.
- **Your question** (text box) — the natural-language question; Enter or the **Ask** button submits.

**Output fields:**
- **Answer** (text box) — the grounded, generated answer.
- **Retrieved from** (text box) — the source documents the answer drew from (attribution).

**Sample interaction transcript:**
```
Professor:  Awrad Ali
CS1 only:   ☐ (unchecked)
Question:   Is the grading fair or harsh?

[Ask]

Answer:
  The reviews disagree on whether the grading is considered fair or harsh. Some
  students consider it fair (the lowest quiz grade is dropped; exams hard but fair),
  while others consider it harsh (zeros for suspected AI use; a 50% grade for getting
  peer help; poorly organized exams).

Retrieved from:
  • RMP — Awrad Ali
```

---

## Evaluation Report

Run reproducibly with `python3 -m eval.run_eval`. Filters reflect what a user would
pick in the UI (single-professor questions filter to that professor; comparison/general
questions use no professor filter; "best for CS1" and "general difficulty" use CS1-only).

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | Which professors provide extra credit? | Ahmed, Ali, Rahaman | Names **Ahmed** only (cites several reviews); states no extra-credit mention for Guha, Rahaman, or Ali | Partially relevant | **Partially accurate** |
| 2 | Between Ali and Ahmed, whose class seems harder? | Ahmed | Concludes **Ahmed** is harder, citing his difficult exams/heavy assignments vs. milder Ali reviews | Partially relevant (imbalanced) | **Accurate** |
| 3 | Overall, who is the best professor for CS1? | Guha / Ahmed | "No clear consensus"; highlights **Ahmed**, Rahaman, Ali; Guha not surfaced | Relevant | **Partially accurate** |
| 4 | Is Awrad Ali's grading fair or harsh? | Fair | Balanced: several reviews say fair (drops lowest quiz, fair-but-hard exams), several say harsh (AI-use zeros, tight timing). Sources: only Awrad Ali | Relevant | **Accurate** |
| 5 | In general, how difficult are the CS1 professors? | Fair / moderate | Varies: Ahmed/Guha harder, Kullu/Rahaman easier; CS1 rigorous regardless of professor | Relevant | **Accurate** |

**Retrieval quality:** Relevant / Partially relevant / Off-target
**Response accuracy:** Accurate / Partially accurate / Inaccurate

Notes: Q2, Q4, and Q5 are strong — grounded, correctly attributed, and the professor
filter on Q4 returned only Awrad Ali (no leakage). Q2 reached the right conclusion
(Ahmed), though its retrieval was imbalanced (see Failure Case). Q1 and Q3 are *grounded
but incomplete*; **Q1 is the documented failure analyzed below**.

---

## Failure Case Analysis

**Question that failed:** Q1 — "Which professors provide extra credit?"
(Expected: **Ahmed, Ali, Rahaman**.)

**What the system returned:** It named **only Tanvir Ahmed**, citing several of his reviews,
and explicitly stated there was "no mention of extra credit in the reviews for Professors
Arup Guha, Md Mahfuzur Rahaman, or Awrad Ali." This is verifiably wrong for at least
Rahaman: his corpus contains an explicit review reading *"Gave us so many opportunities for
extra credit and gave really great curves…"* — that review exists in the data but was never
shown to the model.

**Root cause (tied to a specific pipeline stage):** This is a **retrieval recall** failure
driven by **corpus imbalance**, not a generation failure. "Which professors give extra
credit?" is an *aggregate* question whose correct answer is spread across several
professors, but retrieval returns the top-k=10 chunks closest to the query *globally*,
ranked only by cosine similarity. Ahmed has **233 CS1 reviews** (many mentioning extra
credit) versus Rahaman's **9** and Ali's **18**. Ahmed's many extra-credit reviews are all
strong matches, so they **crowd out** the top-10 and the rare extra-credit mentions from the
sparse professors never rank high enough to be retrieved. The LLM then answered faithfully
from what it was given — almost entirely Ahmed — so it correctly (per its grounding rules)
reported that the others don't offer extra credit. The model did its job; retrieval simply
never surfaced the evidence. This is the same imbalance that made Q2's retrieval one-sided —
there it happened to favor the correct answer, here it produced a wrong one. (The Retrieval
Test Results "Query C" above shows the symptom directly: even when filtered to Rahaman, his
explicit extra-credit review didn't rank in the top results.)

**What I would change to fix it:** For aggregate "which professors…" questions, retrieve a
**balanced top-k per professor** — loop over the five professors and pull each one's top-n
chunks (`where professor == X`), then merge — instead of one global top-10. That guarantees
every professor's most relevant reviews are represented regardless of how many total reviews
they have. A lighter alternative is **diversity-aware retrieval** (e.g. MMR) so the top-k
isn't filled with near-duplicate Ahmed reviews, or simply raising k for aggregate queries.
All of these fix the problem at the retrieval stage, where it originates — the embedding,
chunking, and generation stages all behaved correctly.

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
