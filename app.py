"""The Unofficial Guide — Gradio interface (Milestone 5).

Pipeline (from planning.md): user question + professor from dropdown
    -> metadata filter -> retrieve top-k -> grounded generation -> display answer + sources.

Run:  python3 app.py   then open http://localhost:7860
"""

import gradio as gr

from rag.generate import PROFESSORS, ask

ALL = "All professors"


def handle_query(question: str, professor: str, cs1_only: bool):
    question = (question or "").strip()
    if not question:
        return "Please enter a question.", ""

    prof = None if professor == ALL else professor
    result = ask(question, professor=prof, is_cs1=cs1_only)

    sources = result["sources"]
    sources_md = "\n".join(f"• {s}" for s in sources) if sources else "(no sources — question not covered by the reviews)"
    return result["answer"], sources_md


with gr.Blocks(title="The Unofficial Guide — UCF CS1 Professors") as demo:
    gr.Markdown(
        "# 🎓 The Unofficial Guide — UCF CS1 (COP 3502) Professors\n"
        "Ask about teaching style, difficulty, grading, or extra credit. Answers come "
        "**only** from real student reviews (RateMyProfessors + Reddit). "
        "Pick a professor to focus on one, or leave it on *All professors* to compare."
    )

    with gr.Row():
        professor = gr.Dropdown(
            choices=[ALL] + PROFESSORS, value=ALL, label="Professor"
        )
        cs1_only = gr.Checkbox(
            value=False, label="CS1 (COP 3502) reviews only"
        )

    question = gr.Textbox(
        label="Your question",
        placeholder="e.g. Is Awrad Ali's grading fair or harsh?",
    )
    ask_btn = gr.Button("Ask", variant="primary")

    answer = gr.Textbox(label="Answer", lines=8)
    sources = gr.Textbox(label="Retrieved from", lines=4)

    gr.Examples(
        examples=[
            ["Which professors give extra credit?", ALL, False],
            ["Is the grading fair or harsh?", "Awrad Ali", False],
            ["Who is the best professor for CS1?", ALL, True],
            ["How difficult are the exams and workload?", "Tanvir Ahmed", False],
        ],
        inputs=[question, professor, cs1_only],
    )

    inputs = [question, professor, cs1_only]
    outputs = [answer, sources]
    ask_btn.click(handle_query, inputs=inputs, outputs=outputs)
    question.submit(handle_query, inputs=inputs, outputs=outputs)


if __name__ == "__main__":
    demo.launch()
