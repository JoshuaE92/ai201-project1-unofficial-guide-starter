"""Milestone 6 — run the 5 planning.md evaluation questions end-to-end.

Each question is run through ask() exactly as the Gradio UI would, using the
professor filter a user would naturally pick (single-professor questions filter
to that professor; comparison/general questions use no filter). Prints the
question, the filter used, the system answer, and the programmatic sources so the
results can be transcribed into the README Evaluation Report.

Run:  python3 -m eval.run_eval
"""

from rag.generate import ask

# (question, professor filter or None, is_cs1, expected answer from planning.md)
EVAL = [
    ("Which professors provide extra credit?", None, False, "Ahmed, Ali, Rahaman"),
    ("Between Awrad Ali and Tanvir Ahmed, whose class seems harder?", None, False, "Ali"),
    ("Overall, who is the best professor for CS1?", None, True, "Guha / Ahmed"),
    ("Is the grading considered fair or harsh?", "Awrad Ali", False, "Fair"),
    ("In general, how difficult are the CS1 professors?", None, True, "Fair / moderate"),
]


def main() -> None:
    for i, (q, prof, cs1, expected) in enumerate(EVAL, 1):
        r = ask(q, professor=prof, is_cs1=cs1)
        flt = prof or "All professors"
        if cs1:
            flt += " + CS1-only"
        print(f"\n{'='*84}\nQ{i}: {q}")
        print(f"   filter: {flt}   |   expected: {expected}")
        print(f"\nANSWER:\n{r['answer']}")
        print(f"\nSOURCES: {r['sources']}")


if __name__ == "__main__":
    main()
