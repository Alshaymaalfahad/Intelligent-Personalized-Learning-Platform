"""📖 The briefing before each learning activity: «أنا أشرح ← نسوي سوا ← أنت تسوي».

Stations: 🎬 why it matters → 📖 I explain → 🤝 we do it together (the trainee
completes the last step) → ✅ quick check (not graded) → 🎮 the activity → 🏆 boss.

The depth follows the gap type (from the skill/knowledge contrast); the style is
the trainee's choice, and the style that works best for them is suggested next time.
"""

import json
import random

from sqlalchemy.orm import Session

from .activity_schemas import LessonContent
from .assessment_engine import EngineError
from .gap_analyzer import TARGET_SCORE
from .learning_engine import gap_context, journey_step
from .models import Assessment, LearningActivity, Lesson
from .question_generator import generate_validated, render_prompt

DEPTHS = {
    "compound": {
        "label": "فجوة مركّبة",
        "description": "تحتاج المفهوم والتطبيق معًا: سنشرح المفهوم من الأساس، ثم مثالًا محلولًا.",
        "prompt": "Compound gap (does not know AND does not apply): explain the concept from the basics in 3–5 sections, then the worked example.",
    },
    "application": {
        "label": "فجوة تطبيق",
        "description": "تعرف المفهوم لكن التطبيق يحتاج تدريبًا: تذكير سريع، والتركيز على المثال المحلول.",
        "prompt": "Application gap (knows the concept but does not apply it): only a quick reminder of the concept in 1–2 short sections; put the weight on the worked example and on HOW to apply it.",
    },
    "shallow": {
        "label": "فهم سطحي",
        "description": "تطبّق القاعدة لكن «الليش» وراءها غير واضح: سنشرح السبب لا القاعدة فقط.",
        "prompt": "Shallow understanding (applies the rule but not the reasoning): explain the WHY behind the rule in 2–3 sections — causes, consequences, when the rule does NOT apply.",
    },
    "mastery": {
        "label": "إتقان مبدئي",
        "description": "مستواك قريب من المطلوب: تقدر تتخطى الشرح وتدخل التحدي مباشرة، والشرح متاح متى احتجته.",
        "prompt": "Initial mastery: a compact recap in 1–2 sections focused on the subtle points experienced people still miss.",
    },
}

STYLES = {
    "brief": {
        "label": "📄 شرح مختصر",
        "prompt": "Brief: clear, compact paragraphs with a heading each; the most direct path to understanding.",
    },
    "story": {
        "label": "📚 قصة من العمل",
        "prompt": "Story: teach through a short story of a colleague facing this exact problem at work; each section is one beat of the story, and the lesson emerges from what happened and why.",
    },
    "visual": {
        "label": "🗺️ إنفوجرافيك",
        "prompt": "Visual (infographic): each section is a compact visual block — a fitting emoji, a 2–5 word heading, and at most 2 short lines (comparisons, flows like «أ ← ب ← ج», do/don't). No long paragraphs.",
    },
    "interactive": {
        "label": "🧪 مثال تفاعلي",
        "prompt": "Interactive: each section starts with `reveal_question` — a short question the trainee thinks about first (e.g. «برأيك، هل هذا الرقم خطأ؟») — and the `body` is the answer and the reasoning, revealed when they click.",
    },
}


def depth_for(assessment: Assessment, competency_id: str) -> str:
    """Gap type from the operational concept: compare the skill with its related knowledge."""
    report = assessment.report
    results = {r["competency_id"]: r for r in report["skill_results"] + report["knowledge_results"] + report.get("new_gaps", [])}
    r = results[competency_id]
    progress = (assessment.learning_progress or {}).get(competency_id, {})
    if progress.get("current", r["score"]) >= TARGET_SCORE:
        return "mastery"
    if r.get("origin"):  # a new gap found in reassessment: detects but cannot justify
        return "shallow"
    if r["dimension"] == "skill":
        related = [k["score"] for k in report["knowledge_results"] if competency_id in k.get("related_skill_ids", [])]
        if related:
            return "application" if sum(related) / len(related) >= TARGET_SCORE else "compound"
        return "compound" if r["status"] == "likely_gap" else "application"
    related = [results[s]["score"] for s in r.get("related_skill_ids", []) if s in results]
    if related and max(related) >= TARGET_SCORE:
        return "shallow"
    return "compound"


def _style_scores(db: Session, assessment: Assessment) -> dict[str, float]:
    """How well each style worked for this trainee: quick-check first tries (40%) and
    the boss result of activities on the same gap afterwards (60%)."""
    lessons = db.query(Lesson).join(Assessment).filter(Assessment.trainee_pk == assessment.trainee_pk).all()
    scores: dict[str, list[float]] = {}
    for lesson in lessons:
        if not lesson.completed:
            continue
        content = lesson.content
        answers = lesson.check_answers or []
        check = sum(a == q["correct"] for a, q in zip(answers, content["check"])) / len(content["check"]) if content["check"] else 0
        later = [
            a.result["boss_percent"] / 100 for a in db.query(LearningActivity).filter(
                LearningActivity.assessment_pk == lesson.assessment_pk,
                LearningActivity.competency_id == lesson.competency_id,
                LearningActivity.status == "completed",
            ) if a.result and a.created_at >= lesson.created_at
        ]
        value = 0.4 * check + 0.6 * (later[0] if later else check)
        scores.setdefault(lesson.style, []).append(value)
    return {style: round(sum(v) / len(v), 2) for style, v in scores.items()}


def suggested_style(db: Session, assessment: Assessment) -> str | None:
    scores = _style_scores(db, assessment)
    return max(scores, key=scores.get) if scores else None


def current(db: Session, assessment: Assessment, competency_id: str) -> Lesson | None:
    return (
        db.query(Lesson)
        .filter(Lesson.assessment_pk == assessment.id, Lesson.competency_id == competency_id)
        .order_by(Lesson.id.desc())
        .first()
    )


def validate(c: LessonContent, depth: str, style: str) -> list[str]:
    p = []
    for name in ("why_title", "why_story", "why_impact", "explanation_title", "example_problem", "final_step_question", "final_step_explanation"):
        if not getattr(c, name).strip():
            p.append(f"{name} is required.")
    lo, hi = {"compound": (3, 5), "application": (1, 2), "shallow": (2, 3), "mastery": (1, 2)}[depth]
    if not lo <= len(c.sections) <= hi:
        p.append(f"sections: {lo}-{hi} for this depth.")
    if any(not s.heading.strip() or not s.body.strip() for s in c.sections):
        p.append("every section needs a heading and a body.")
    if style == "interactive" and any(not s.reveal_question.strip() for s in c.sections):
        p.append("interactive style: every section needs a reveal_question.")
    if len(c.takeaways) != 3:
        p.append("exactly 3 takeaways.")
    if not 2 <= len(c.example_steps) <= 4:
        p.append("example_steps: 2-4 solved steps.")
    if len(c.final_step_options) != 3 or len(set(c.final_step_options)) != 3 or not 0 <= c.final_step_correct < 3:
        p.append("final step: 3 distinct options and a valid correct index.")
    if not 1 <= len(c.check) <= 2:
        p.append("check: 1-2 questions.")
    for q in c.check:
        if not 3 <= len(q.options) <= 4 or len(set(q.options)) != len(q.options) or not 0 <= q.correct < len(q.options):
            p.append("each check question needs 3-4 distinct options and a valid correct index.")
            break
    return p


def _shuffle(options: list[str], correct: int) -> tuple[list[str], int]:
    order = list(range(len(options)))
    random.shuffle(order)
    return [options[i].strip() for i in order], order.index(correct)


def create(db: Session, assessment: Assessment, competency_id: str, style: str) -> Lesson:
    if style not in STYLES:
        raise EngineError(422, "أسلوب شرح غير معروف.")
    if assessment.status != "completed":
        raise EngineError(409, "أكمل التقييم أولًا.")
    journey_step(assessment, competency_id)
    depth = depth_for(assessment, competency_id)
    ctx = gap_context(assessment, competency_id)
    prompt = render_prompt(
        "lesson.txt",
        specialization=assessment.trainee.specialization,
        competency=json.dumps(ctx["competency"], ensure_ascii=False),
        gap_evidence=json.dumps(ctx["evidence"], ensure_ascii=False, indent=2) if ctx["evidence"] else "(no wrong answers recorded)",
        depth=depth,
        depth_instructions=DEPTHS[depth]["prompt"],
        style=style,
        style_instructions=STYLES[style]["prompt"],
    )
    out = generate_validated(prompt, LessonContent, lambda c: validate(c, depth, style), task="lesson")
    content = out.model_dump()
    content["final_step_options"], content["final_step_correct"] = _shuffle(out.final_step_options, out.final_step_correct)
    for q in content["check"]:
        q["options"], q["correct"] = _shuffle(q["options"], q["correct"])
    lesson = Lesson(assessment_pk=assessment.id, competency_id=competency_id, depth=depth, style=style, content=content)
    db.add(lesson)
    db.flush()
    lesson.lesson_id = f"LS-{lesson.id:04d}"
    db.commit()
    return lesson


def answer_final_step(db: Session, lesson: Lesson, choice: int) -> dict:
    c = lesson.content
    if not 0 <= choice < len(c["final_step_options"]):
        raise EngineError(422, "اختر خيارًا.")
    if lesson.final_step_answer is None:
        lesson.final_step_answer = choice  # first try only, for the style signal
        db.commit()
    return {"correct": choice == c["final_step_correct"], "correct_index": c["final_step_correct"], "explanation": c["final_step_explanation"]}


def answer_check(db: Session, lesson: Lesson, index: int, choice: int) -> dict:
    c = lesson.content
    if not 0 <= index < len(c["check"]) or not 0 <= choice < len(c["check"][index]["options"]):
        raise EngineError(422, "اختر خيارًا.")
    answers = list(lesson.check_answers or [None] * len(c["check"]))
    if answers[index] is None:
        answers[index] = choice
        lesson.check_answers = answers
        db.commit()
    q = c["check"][index]
    return {"correct": choice == q["correct"], "correct_index": q["correct"], "explanation": q["explanation"]}


def complete(db: Session, lesson: Lesson) -> None:
    lesson.completed = True
    db.commit()


def view(lesson: Lesson) -> dict:
    """Answers are hidden until the trainee answers (the endpoints return them)."""
    c = lesson.content
    return {
        "lesson_id": lesson.lesson_id,
        "competency_id": lesson.competency_id,
        "depth": lesson.depth,
        "depth_label": DEPTHS[lesson.depth]["label"],
        "depth_description": DEPTHS[lesson.depth]["description"],
        "style": lesson.style,
        "style_label": STYLES[lesson.style]["label"],
        "completed": lesson.completed,
        "why": {"title": c["why_title"], "story": c["why_story"], "impact": c["why_impact"]},
        "explanation": {"title": c["explanation_title"], "sections": c["sections"], "takeaways": c["takeaways"]},
        "example": {
            "problem": c["example_problem"], "lines": c["example_lines"], "steps": c["example_steps"],
            "final_question": c["final_step_question"], "final_options": c["final_step_options"],
        },
        "check": [{"question": q["question"], "options": q["options"]} for q in c["check"]],
    }


def status(db: Session, assessment: Assessment, competency_id: str) -> dict:
    """What the activity page needs before the activity: depth, styles, and any existing lesson."""
    journey_step(assessment, competency_id)
    depth = depth_for(assessment, competency_id)
    lesson = current(db, assessment, competency_id)
    return {
        "depth": depth,
        "depth_label": DEPTHS[depth]["label"],
        "depth_description": DEPTHS[depth]["description"],
        "can_skip": depth == "mastery",
        "styles": [{"id": k, "label": v["label"]} for k, v in STYLES.items()],
        "suggested_style": suggested_style(db, assessment),
        "lesson": view(lesson) if lesson else None,
    }
