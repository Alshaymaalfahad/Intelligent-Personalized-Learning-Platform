"""Adaptive assessment state machine — one question at a time.

Per section (skill, then knowledge):

    <entry> ─start─▶ preparing ─▶ question ─answer─▶ grading ─▶ answered ─next─▶ generating ─▶ question …
                                                                         └─(10 answered)─▶ <done>

  skill:     entry = created,      done = skill_done
  knowledge: entry = skill_done,   done = completed

The AI writes plans and questions; this module and adaptive_selector decide what
happens and when. Every transition is claimed atomically (UPDATE … WHERE status = …),
so a double click or two tabs cannot trigger two paid AI calls for the same step.
If an AI step fails, the status returns to the last stable state so it can be retried.
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, or_, update
from sqlalchemy.orm import Session

from . import config
from .adaptive_selector import QUESTIONS_PER_SECTION, QUESTIONS_PER_SKILL, next_knowledge_target, next_skill_target
from .answer_evaluator import grade_choice, grade_open_answers, grade_ordering
from .gap_analyzer import build_report, competency_results
from .i18n import lang_of
from .models import Assessment, Question, Trainee, utcnow
from .question_generator import plan_knowledge, plan_skills, write_question

# A transient status older than this is assumed to belong to a crashed request.
STALE_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class PhaseFlow:
    entry: str
    preparing: str
    question: str
    grading: str
    answered: str
    generating: str
    done: str
    id_prefix: str
    position_offset: int


PHASES = {
    "skill": PhaseFlow(
        "created", "preparing_skill", "skill_question", "grading_skill", "skill_answered", "generating_skill",
        "skill_done", "SQ", 0,
    ),
    "knowledge": PhaseFlow(
        "skill_done", "preparing_knowledge", "knowledge_question", "grading_knowledge", "knowledge_answered",
        "generating_knowledge", "completed", "KQ", 100,
    ),
}


class EngineError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _claim(db: Session, assessment: Assessment, expected: str, new: str) -> bool:
    stale_before = utcnow() - STALE_AFTER
    result = db.execute(
        update(Assessment)
        .where(
            Assessment.id == assessment.id,
            or_(
                Assessment.status == expected,
                and_(Assessment.status == new, Assessment.updated_at < stale_before),
            ),
        )
        .values(status=new, updated_at=utcnow())
    )
    db.commit()
    db.refresh(assessment)
    return result.rowcount == 1


def _reset_status(db: Session, assessment: Assessment, status: str) -> None:
    db.rollback()
    db.refresh(assessment)
    assessment.status = status
    db.commit()


def _claim_or_fail(db: Session, assessment: Assessment, expected: str, new: str) -> None:
    if not _claim(db, assessment, expected, new):
        if assessment.status == new:
            raise EngineError(409, "جارٍ تنفيذ هذه الخطوة بالفعل، انتظر قليلًا.")
        raise EngineError(409, "لا يمكن تنفيذ هذه الخطوة في المرحلة الحالية من التقييم.")


def create_assessment(db: Session, trainee: Trainee) -> Assessment:
    assessment = Assessment(trainee=trainee, status="created")
    db.add(assessment)
    db.flush()
    assessment.assessment_id = f"AS-{assessment.id:04d}"
    db.commit()
    return assessment


def pending_question(assessment: Assessment, phase: str) -> Question | None:
    return next((q for q in assessment.phase_questions(phase) if q.trainee_answer is None), None)


def _answered(assessment: Assessment, phase: str) -> list[Question]:
    return [q for q in assessment.phase_questions(phase) if q.trainee_answer is not None]


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _blueprint(assessment: Assessment, phase: str) -> list[dict]:
    return (assessment.skill_blueprint if phase == "skill" else assessment.knowledge_blueprint) or []


def is_reassessment(assessment: Assessment) -> bool:
    return assessment.kind == "reassessment"


def section_total(assessment: Assessment, phase: str) -> int:
    """10 questions per section in the first assessment; 2 per competency in a reassessment."""
    if phase == "skill" or is_reassessment(assessment):
        return len(_blueprint(assessment, phase)) * QUESTIONS_PER_SKILL
    return QUESTIONS_PER_SECTION


def _finish_report(assessment: Assessment, knowledge_answered: list[Question]) -> None:
    knowledge = competency_results(assessment.knowledge_blueprint or [], knowledge_answered, "knowledge")
    if is_reassessment(assessment):
        from .reassessment import build_reassessment_report

        assessment.report = build_reassessment_report(assessment, assessment.skill_results or [], knowledge)
    else:
        assessment.report = build_report(assessment, assessment.skill_results, knowledge)


def _add_next_question(db: Session, assessment: Assessment, phase: str) -> None:
    """Ask the selector for the next target and have the AI write the question."""
    flow = PHASES[phase]
    answered = _answered(assessment, phase)
    blueprint = _blueprint(assessment, phase)
    extra_history, context = [], None
    start_difficulty, start_bloom = None, None
    if is_reassessment(assessment):
        from .reassessment import parent_question_texts, question_context, starting_points

        start_difficulty, start_bloom = starting_points(assessment)
        extra_history = parent_question_texts(assessment)
    if phase == "skill":
        target = next_skill_target(blueprint, answered, start_difficulty)
    else:
        target = next_knowledge_target(
            blueprint, answered, assessment.skill_results or [], section_total(assessment, phase), start_bloom
        )
    if is_reassessment(assessment):
        context = question_context(assessment, target.competency_id)
        if not target.previous_on_competency:
            target.reason = "Reassessment: a new situation the trainee has not seen, to verify transfer of learning. " + target.reason
            target.reason_code = {**target.reason_code, "params": {**target.reason_code.get("params", {}), "reassessment": True}}
    competency = next(c for c in blueprint if c["competency_id"] == target.competency_id)
    position = len(answered) + 1

    fields = write_question(
        assessment.trainee, phase, target, competency, list(assessment.questions), position,
        total=section_total(assessment, phase), extra_history=extra_history, reassessment_context=context,
    )

    db.refresh(assessment, ["questions"])
    if pending_question(assessment, phase):  # a stale-claimed duplicate request finished first
        return
    assessment.questions.append(Question(
        question_id=f"{flow.id_prefix}-{position:02d}",
        phase=phase,
        position=flow.position_offset + position,
        **fields,
    ))
    assessment.ai_model = f"{config.AI_PROVIDER}:{config.AI_MODEL}"


def start_section(db: Session, assessment: Assessment, phase: str) -> None:
    """Plan the section (hidden from the trainee) and write its first question."""
    flow = PHASES[phase]
    if assessment.status in (flow.question, flow.answered):
        return  # already started — idempotent, safe after a page refresh
    _claim_or_fail(db, assessment, flow.entry, flow.preparing)
    try:
        if not _blueprint(assessment, phase):
            trainee = assessment.trainee
            if phase == "skill":
                assessment.skill_blueprint = [s.model_dump() for s in plan_skills(trainee).skills]
            else:
                plan = plan_knowledge(trainee, assessment.skill_blueprint, assessment.skill_results)
                assessment.knowledge_blueprint = [a.model_dump() for a in plan.knowledge_areas]
                assessment.adaptation_summary = plan.adaptation_summary.strip()
            db.commit()  # keep the plan even if the first question fails
        _add_next_question(db, assessment, phase)
        assessment.status = flow.question
        db.commit()
    except Exception:
        db.rollback()
        db.refresh(assessment)
        _reset_status(db, assessment, flow.entry)
        raise


def _check_answer(q: Question, answer: int | str) -> None:
    if q.is_open:
        if not isinstance(answer, str) or not answer.strip():
            raise EngineError(422, "اكتب إجابتك قبل المتابعة.")
    elif q.is_ordering:
        if not isinstance(answer, list) or sorted(answer) != list(range(len(q.options))):
            raise EngineError(422, "رتّب جميع العناصر قبل المتابعة.")
    elif isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer < len(q.options):
        raise EngineError(422, "اختر إجابة صالحة.")


def submit_answer(db: Session, assessment: Assessment, phase: str, question_id: str, answer: int | str) -> None:
    """Grade the answer, then immediately prepare the next question (or finish the section)."""
    flow = PHASES[phase]
    if assessment.status != flow.question:
        raise EngineError(409, "لا يوجد سؤال بانتظار الإجابة في هذه المرحلة.")
    q = pending_question(assessment, phase)
    if q is None or q.question_id != question_id.upper():
        raise EngineError(409, "هذا السؤال لم يعد السؤال الحالي. حدّث الصفحة.")
    _check_answer(q, answer)

    _claim_or_fail(db, assessment, flow.question, flow.grading)
    try:
        q = pending_question(assessment, phase)
        q.trainee_answer = answer
        if q.is_open:
            grade_open_answers([q], assessment.trainee.specialization, lang_of(assessment.trainee))
        elif q.is_ordering:
            grade_ordering(q)
        else:
            grade_choice(q)
        assessment.status = flow.answered
        db.commit()
    except Exception:
        db.rollback()
        db.refresh(assessment)
        _reset_status(db, assessment, flow.question)
        raise

    advance(db, assessment, phase)


def advance(db: Session, assessment: Assessment, phase: str) -> None:
    """From `answered`: write the next question, or close the section after the last one."""
    flow = PHASES[phase]
    if assessment.status in (flow.question, flow.done):
        return  # idempotent
    _claim_or_fail(db, assessment, flow.answered, flow.generating)
    try:
        answered = _answered(assessment, phase)
        if len(answered) >= section_total(assessment, phase):
            if phase == "skill":
                assessment.skill_results = competency_results(assessment.skill_blueprint, answered, "skill")
                if is_reassessment(assessment) and not assessment.knowledge_blueprint:
                    _finish_report(assessment, [])  # nothing left to measure
                    assessment.status = "completed"
                else:
                    assessment.status = flow.done
            else:
                _finish_report(assessment, answered)
                assessment.status = flow.done
        else:
            _add_next_question(db, assessment, phase)
            assessment.status = flow.question
        db.commit()
    except Exception:
        db.rollback()
        db.refresh(assessment)
        _reset_status(db, assessment, flow.answered)
        raise


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def current_phase(status: str) -> str | None:
    """The section the trainee is in or about to start."""
    if status == "skill_done":
        return "knowledge"
    for name, flow in PHASES.items():
        if status in (flow.entry, flow.preparing, flow.question, flow.grading, flow.answered, flow.generating):
            return name
    return None


def public_question(q: Question) -> dict:
    """What the trainee sees: no competency, level, correct answer, rubric or rationale."""
    return {
        "question_id": q.question_id,
        "question_type": q.question_type,
        "question_text": q.question_text,
        "code_snippet": q.code_snippet,
        "options": q.options,
        "answer_format": "text" if q.is_open else "order" if q.is_ordering else "choice",
    }


def state_view(assessment: Assessment) -> dict:
    phase = current_phase(assessment.status)
    view = {
        "assessment_id": assessment.assessment_id,
        "trainee_id": assessment.trainee.trainee_id,
        "status": assessment.status,
        "kind": assessment.kind or "initial",
        "phase": phase,
        "total": section_total(assessment, phase) if phase else QUESTIONS_PER_SECTION,
        "sections": {
            name: {"total": section_total(assessment, name), "answered": len(_answered(assessment, name))}
            for name in PHASES
        },
        "answered": 0,
        "question": None,
    }
    if phase:
        view["answered"] = len(_answered(assessment, phase))
        if assessment.status == PHASES[phase].question:
            q = pending_question(assessment, phase)
            view["question"] = public_question(q) if q else None
    return view


def review_view(assessment: Assessment) -> dict:
    """Everything, including correct answers and the adaptive path — only once completed."""
    names = {c["competency_id"]: c["name"] for c in (assessment.skill_blueprint or []) + (assessment.knowledge_blueprint or [])}
    kinds = {c["competency_id"]: c["skill_kind"] for c in assessment.skill_blueprint or []}
    return {
        "assessment_id": assessment.assessment_id,
        "ai_model": assessment.ai_model,
        "trainee": {
            "trainee_id": assessment.trainee.trainee_id,
            "specialization": assessment.trainee.specialization,
            "interests": assessment.trainee.interests,
            "additional_message": assessment.trainee.additional_message,
        },
        "skill_blueprint": assessment.skill_blueprint,
        "knowledge_blueprint": assessment.knowledge_blueprint,
        "adaptation_summary": assessment.adaptation_summary,
        "questions": [
            {
                **public_question(q),
                "phase": q.phase,
                "competency_id": q.competency_id,
                "competency_name": names.get(q.competency_id, q.competency_id),
                "skill_kind": kinds.get(q.competency_id),
                "bloom_level": q.bloom_level,
                "difficulty": q.difficulty,
                "adaptation_reason": q.adaptation_reason,
                "adaptation_code": q.adaptation_code,
                "learning_objective": q.learning_objective,
                "correct_option_index": q.correct_option_index,
                "correct_order": q.correct_order,
                "reference_answer": q.reference_answer,
                "scoring_rubric": q.scoring_rubric,
                "rationale": q.rationale,
                "max_score": q.max_score,
                "trainee_answer": q.trainee_answer,
                "earned_score": q.earned_score,
                "grading_confidence": q.grading_confidence,
                "grading_details": q.grading_details,
                "feedback": q.feedback,
                "review_rating": q.review_rating,
                "review_note": q.review_note,
            }
            for q in assessment.questions
        ],
    }
