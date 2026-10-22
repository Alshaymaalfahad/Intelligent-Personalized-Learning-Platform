"""Grades answers.

Choice and ordering questions are graded deterministically on the server. Open-ended answers
are graded by the AI against the question's rubric; the server then clamps every
awarded value to the rubric's limits and recomputes the totals itself.
"""

from .ai_client import AIOutputInvalid
from .models import Question
from .question_generator import generate_validated, render_prompt
from .schemas import OpenAnswerEvaluationOutput

EMPTY_ANSWER_FEEDBACK = {"en": "No answer was given.", "ar": "لم تُقدَّم إجابة."}


def grade_ordering(q: Question) -> None:
    """Partial credit by pairwise agreement, rescaled so a random order scores ~0:
    exact order = 1, fully reversed = 0."""
    position = {item: i for i, item in enumerate(q.trainee_answer)}
    seq = q.correct_order
    pairs = [(a, b) for i, a in enumerate(seq) for b in seq[i + 1:]]
    agreement = sum(1 for a, b in pairs if position[a] < position[b]) / len(pairs)
    q.earned_score = round(q.max_score * max(0.0, (agreement - 0.5) * 2), 2)
    q.grading_confidence = 1.0
    q.grading_details = None
    q.feedback = None


def grade_choice(q: Question) -> None:
    correct = q.trainee_answer == q.correct_option_index
    q.earned_score = q.max_score if correct else 0.0
    q.grading_confidence = 1.0
    q.grading_details = None
    q.feedback = None


def _render_item(q: Question) -> str:
    rubric = "\n".join(f"  {i + 1}. {c['criterion']} — {c['points']} point(s)" for i, c in enumerate(q.scoring_rubric))
    code = f"\nCode shown with the question:\n```\n{q.code_snippet}\n```" if q.code_snippet else ""
    answer = str(q.trainee_answer).replace("<", "‹").replace(">", "›")
    return (
        f'<question question_id="{q.question_id}">\n'
        f"Question: {q.question_text}{code}\n"
        f"Reference answer elements: {q.reference_answer}\n"
        f"Rubric:\n{rubric}\n"
        f"<trainee_answer>\n{answer}\n</trainee_answer>\n"
        f"</question>"
    )


def grade_open_answers(questions: list[Question], specialization: str, lang: str = "en") -> None:
    """Grade all open-ended questions of a section in a single AI call."""
    to_grade = []
    for q in questions:
        if str(q.trainee_answer or "").strip():
            to_grade.append(q)
        else:
            q.earned_score, q.grading_confidence, q.feedback = 0.0, 1.0, EMPTY_ANSWER_FEEDBACK[lang]
            q.grading_details = [
                {"criterion": c["criterion"], "points": c["points"], "awarded": 0, "justification": EMPTY_ANSWER_FEEDBACK[lang]}
                for c in q.scoring_rubric
            ]
    if not to_grade:
        return

    by_id = {q.question_id: q for q in to_grade}

    def validate(out: OpenAnswerEvaluationOutput) -> list[str]:
        problems = []
        returned = {e.question_id: e for e in out.evaluations}
        for qid, q in by_id.items():
            e = returned.get(qid)
            if e is None:
                problems.append(f"Missing evaluation for question_id {qid}.")
            elif len(e.criteria_scores) != len(q.scoring_rubric):
                problems.append(f"{qid}: expected {len(q.scoring_rubric)} criteria_scores, got {len(e.criteria_scores)}.")
        return problems

    prompt = render_prompt(
        "open_answer_evaluation.txt",
        lang=lang,
        specialization=specialization,
        items="\n\n".join(_render_item(q) for q in to_grade),
    )
    out = generate_validated(prompt, OpenAnswerEvaluationOutput, validate, task="open_answer_evaluation")

    for e in out.evaluations:
        q = by_id.get(e.question_id)
        if q is None:
            continue
        details = []
        for criterion, scored in zip(q.scoring_rubric, e.criteria_scores):
            awarded = max(0, min(scored.awarded, criterion["points"]))
            details.append({
                "criterion": criterion["criterion"],
                "points": criterion["points"],
                "awarded": awarded,
                "justification": scored.justification.strip(),
            })
        q.grading_details = details
        q.earned_score = float(sum(d["awarded"] for d in details))
        q.grading_confidence = max(0.0, min(1.0, e.confidence))
        q.feedback = e.feedback.strip()

    if any(q.earned_score is None for q in to_grade):  # defensive: validate() should prevent this
        raise AIOutputInvalid(["Some open answers were not graded."])
