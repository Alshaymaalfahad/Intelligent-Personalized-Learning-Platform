"""Shared game system for all learning activities: gap context, the end-of-activity
decision (passed / partial / persistent), and journey progress on the assessment.
A gap is only declared closed by the reassessment (reassessment.py).

Activity-specific play (e.g. gap_hunter.py) only has to report how the trainee did
on the boss level; everything that decides whether the gap closed lives here.
"""

import copy

from .adaptive_selector import passed
from .assessment_engine import EngineError
from .gap_analyzer import TARGET_SCORE
from .learning_activities import ACTIVITIES
from .models import Assessment

# New estimate = 40% previous level + 60% boss performance (a new situation, no hints).
PREVIOUS_WEIGHT = 0.4
BOSS_PASS = 70
PARTIAL_BOSS = 50
PARTIAL_GAIN = 10

# The activity can only show readiness: closing a gap needs the independent reassessment.
DECISIONS = {
    "passed": ("✅ اجتزت مرحلة الزعيم", "أحسنت! الفجوة جاهزة للتحقق في إعادة القياس، وفُتحت الخطوة التالية في رحلتك."),
    "partial": ("🔄 قربت!", "تحسّنت بوضوح. جولة أخرى بتلميحات أقل ستثبّت ما تعلمته."),
    "persistent": ("🔀 جرّب طريقة ثانية", "الفجوة ما زالت قائمة، وربما يناسبك أسلوب نشاط مختلف."),
}


def journey_step(assessment: Assessment, competency_id: str) -> dict:
    report = assessment.report or {}
    step = next((s for s in report.get("learning_journey", []) if s["competency_id"] == competency_id), None)
    if step is None:
        raise EngineError(404, "هذه الكفاءة ليست ضمن رحلتك التعليمية.")
    return step


def gap_context(assessment: Assessment, competency_id: str) -> dict:
    """What the activity generator needs to target this specific gap."""
    report = assessment.report
    result = next(
        r for r in report["skill_results"] + report["knowledge_results"] + report.get("new_gaps", [])
        if r["competency_id"] == competency_id
    )
    blueprint = (assessment.skill_blueprint or []) + (assessment.knowledge_blueprint or [])
    definition = next((c for c in blueprint if c["competency_id"] == competency_id), {})
    evidence = []
    for q in assessment.questions:
        if q.competency_id != competency_id or passed(q):
            continue
        item = {"learning_objective": q.learning_objective, "question": q.question_text}
        if q.is_ordering:
            item["correct_order"] = [q.options[i] for i in q.correct_order]
            item["trainee_order"] = [q.options[i] for i in q.trainee_answer]
        elif q.is_open:
            item["grader_feedback"] = q.feedback
        else:
            item["trainee_chose"] = q.options[q.trainee_answer]
            item["correct_answer"] = q.options[q.correct_option_index]
        evidence.append(item)
    progress = (assessment.learning_progress or {}).get(competency_id, {})
    return {
        "competency": {
            "name": result["name"],
            "description": definition.get("description") or result.get("description", ""),
            "dimension": result["dimension"],
            "skill_kind": result.get("skill_kind"),
            "status": result["status"],
        },
        "evidence": evidence,
        "current_score": progress.get("current", result["score"]),
        "status": result["status"],
        "rounds_played": len(progress.get("activities", [])),
    }


def record_result(assessment: Assessment, activity, boss_percent: float) -> dict:
    """Decide whether the gap closed and update the journey progress on the assessment."""
    step = journey_step(assessment, activity.competency_id)
    progress = copy.deepcopy(assessment.learning_progress or {})
    entry = progress.get(activity.competency_id, {"baseline": step["baseline_score"], "activities": []})
    old = entry.get("current", entry["baseline"])
    estimate = round(PREVIOUS_WEIGHT * old + (1 - PREVIOUS_WEIGHT) * boss_percent)
    new = max(old, estimate)  # the game never lowers the trainee's level

    if new >= TARGET_SCORE and boss_percent >= BOSS_PASS:
        decision = "passed"
    elif new - old >= PARTIAL_GAIN or boss_percent >= PARTIAL_BOSS:
        decision = "partial"
    else:
        decision = "persistent"

    tried = set(entry.get("activity_types", [])) | {activity.activity_type}
    alternative = next(
        (a for a in step["alternatives"] if a["activity_type"] not in tried),
        None,
    ) if decision == "persistent" else None

    entry.update({
        "current": new,
        "status": decision,
        "activities": entry.get("activities", []) + [activity.activity_id],
        "activity_types": sorted(tried),
    })
    progress[activity.competency_id] = entry
    assessment.learning_progress = progress

    title, message = DECISIONS[decision]
    return {
        "decision": decision,
        "decision_title": title,
        "decision_message": message,
        "score_before": old,
        "score_after": new,
        "boss_percent": round(boss_percent),
        "target_score": TARGET_SCORE,
        "alternative": alternative,
    }


def check_available(activity_type: str) -> None:
    if not ACTIVITIES[activity_type]["available"]:
        raise EngineError(409, f"نشاط «{ACTIVITIES[activity_type]['name']}» قيد البناء حاليًا.")
