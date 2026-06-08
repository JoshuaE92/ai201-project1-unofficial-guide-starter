"""Milestone 5 — grounded generation.

ask(question, professor, is_cs1, k) is the end-to-end function:
    retrieve relevant review chunks  →  build a grounded prompt  →  call Groq  →
    return {"answer", "sources", "chunks"}.

Grounding is enforced two ways, not suggested:
  1. The system prompt forbids outside knowledge and mandates the exact refusal
     string "I don't have enough information on that." when the reviews don't cover
     the question. Temperature is near 0 so the model follows it.
  2. If retrieval returns nothing (e.g. a professor filter with no matching CS1
     reviews), we short-circuit and return the refusal WITHOUT calling the LLM —
     so it can't invent an answer when there is no evidence.

Source attribution is programmatically guaranteed: `sources` is built from the
metadata of the retrieved chunks, never from whatever the model chooses to write.
"""

import os

from dotenv import load_dotenv
from groq import Groq

from rag.retrieve import retrieve

load_dotenv()

MODEL = "llama-3.3-70b-versatile"
REFUSAL = "I don't have enough information on that."

# Canonical professor names — used for the UI dropdown and the metadata filter.
PROFESSORS = [
    "Tanvir Ahmed",
    "Arup Guha",
    "Awrad Ali",
    "Kurt Kullu",
    "Md Mahfuzur Rahaman",
]

SYSTEM_PROMPT = (
    "You answer questions about University of Central Florida Computer Science 1 "
    "(COP 3502) professors using ONLY the student reviews provided in the user "
    "message. Follow these rules strictly:\n"
    "1. Use only information contained in the provided reviews. Do NOT use any "
    "outside, general, or prior knowledge about these professors or courses.\n"
    f"2. If the reviews do not contain enough information to answer, reply with "
    f"EXACTLY this sentence and nothing else: \"{REFUSAL}\"\n"
    "3. Every claim must be supported by the reviews. Refer to professors by name "
    "when relevant.\n"
    "4. If reviews disagree, say so and summarize both sides. Be concise and "
    "balanced. Do not invent specifics (grades, policies) not present in the reviews."
)

_client = None


def _groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def build_prompt(chunks: list[dict], question: str) -> str:
    """Assemble the retrieved reviews into a numbered, attributed context block."""
    blocks = []
    for i, c in enumerate(chunks, 1):
        prof = c.get("professor") or "unknown professor"
        blocks.append(f"[{i}] (Professor: {prof} — {c['source_name']})\n{c['text']}")
    context = "\n\n".join(blocks)
    return (
        f"Student question: {question}\n\n"
        f"Student reviews you may use (and nothing else):\n\n{context}\n\n"
        f"Answer the question using ONLY these reviews. If they don't cover it, "
        f'reply exactly "{REFUSAL}"'
    )


def call_groq(prompt: str) -> str:
    resp = _groq().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,  # near-deterministic so grounding rules are followed
        max_tokens=600,
    )
    return resp.choices[0].message.content.strip()


def ask(question: str, professor: str = None, is_cs1: bool = False, k: int = 10) -> dict:
    chunks = retrieve(question, professor=professor, is_cs1=is_cs1, k=k)

    # No evidence retrieved -> refuse without calling the LLM (can't ground nothing).
    if not chunks:
        return {"answer": REFUSAL, "sources": [], "chunks": []}

    answer = call_groq(build_prompt(chunks, question))

    # Source attribution is derived from retrieved metadata, not the model output.
    # If the model refused, there's nothing to attribute.
    if answer.strip().rstrip(".") == REFUSAL.rstrip("."):
        sources = []
    else:
        seen, sources = set(), []
        for c in chunks:
            sn = c["source_name"]
            if sn not in seen:
                seen.add(sn)
                sources.append(sn)
    return {"answer": answer, "sources": sources, "chunks": chunks}


if __name__ == "__main__":
    tests = [
        ("Which professors give extra credit?", None),
        ("Is the grading fair or harsh?", "Awrad Ali"),
        ("What do students say about the parking garage by the engineering building?", None),
    ]
    for q, prof in tests:
        r = ask(q, professor=prof)
        print(f"\n{'='*80}\nQ: {q}" + (f"   [professor={prof}]" if prof else ""))
        print(f"\nANSWER:\n{r['answer']}")
        print(f"\nSOURCES: {r['sources']}")
