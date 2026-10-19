"""Reassessment (إعادة القياس) after the learning journey.

A gap is never declared closed from training alone (operational concept, 07 /
REASSESSMENT). Once every journey step is done, the trainee takes an independent
adaptive reassessment: new situations, only for the journey's competencies, two
questions each, steered by the behavior signals recorded during the activities.

The new report compares before → after training → after reassessment for each gap
and gives one of: closed, partial (support continues), persistent (change the
learning method, maybe a human), insufficient evidence — plus any NEW gap that
appeared (e.g. detects mistakes well but cannot justify them).
"""

from sqlalchemy.orm import Session

from .assessment_engine import EngineError
from .behavior import competency_behavior
from .gap_analyzer import STATUS_LABELS, TARGET_SCORE, build_report
from .learning_activities import activity_card, choose_activities
from .models import Assessment

PARTIAL_GAIN = 10
HUMAN_SUPPORT_AFTER = 2  # activities tried before suggesting a human (mentor/trainer)

DECISIONS = {
    "closed": ("✅ أُغلقت الفجوة", "حقق معيار النجاح في مواقف جديدة مع أدلة كافية على أداء مستقل."),
    "partial": ("🔄 تحسن جزئي", "تحسن الأداء لكنه لم يبلغ المعيار بعد؛ يستمر الدعم."),
    "persistent": ("🔀 فجوة مستمرة", "استمر نمط الخطأ؛ نجرّب أسلوب تعلم مختلفًا."),
    "insufficient": ("❔ أدلة غير كافية", "لا تكفي الأدلة للحكم؛ نحتاج قياسًا إضافيًا."),
}


# ---------------------------------------------------------------------------
# Eligibility and creation
# ---------------------------------------------------------------------------

def _child(db: Session, assessment: Assessment) -> Assessment | None:
    return db.query(Assessment).filter(Assessment.parent_pk == assessment.id).order_by(Assessment.id.desc()).first()


def eligibility(db: Session, assessment: Assessment) -> dict:
    steps = (assessment.report or {}).get("learning_journey", [])
    progress = assessment.learning_progress or {}
    done = [
        s for s in steps
        if (p := progress.get(s["competency_id"])) and (p["status"] == "passed" or len(p["activities"]) >= HUMAN_SUPPORT_AFTER)
    ]
    child = _child(db, assessment)
    return {
        "eligible": bool(steps) and len(done) == len(steps),
        "done_steps": len(done),
        "total_steps": len(steps),
        "reassessment_id": child.assessment_id if child else None,
        "reassessment_status": child.status if child else None,
    }


def _knowledge_definition(gap: dict) -> dict:
    """A 'new gap' from an earlier reassessment, measured like a knowledge area."""
    return {
        "competency_id": gap["competency_id"], "name": gap["name"], "description": gap.get("description", gap["name"]),
        "importance": gap.get("importance", 2), "related_skill_ids": [], "selection_reason": "",
    }


def create(db: Session, assessment: Assessment) -> Assessment:
    if assessment.status != "completed":
        raise EngineError(409, "أكمل التقييم أولًا.")
    existing = _child(db, assessment)
    if existing:
        return existing
    info = eligibility(db, assessment)
    if not info["eligible"]:
        raise EngineError(409, f"أكمل خطوات الرحلة التعليمية أولًا ({info['done_steps']} من {info['total_steps']}).")

    report = assessment.report
    results = {r["competency_id"]: r for r in report["skill_results"] + report["knowledge_results"] + report.get("new_gaps", [])}
    skills = {s["competency_id"]: s for s in assessment.skill_blueprint or []}
    areas = {a["competency_id"]: a for a in assessment.knowledge_blueprint or []}
    progress = assessment.learning_progress or {}

    skill_blueprint, knowledge_blueprint, context = [], [], {}
    for step in report["learning_journey"]:
        cid = step["competency_id"]
        p = progress.get(cid, {})
        activities = [a for a in assessment.activities if a.competency_id == cid and a.status == "completed"]
        last_level = activities[-1].levels[-1] if activities else None
        behavior = competency_behavior(db, assessment, cid)
        if step["dimension"] == "skill":
            skill_blueprint.append(skills[cid])
            start = {"difficulty": max(3, last_level["difficulty"]) if last_level else 3}
        else:
            knowledge_blueprint.append(areas.get(cid) or _knowledge_definition(results[cid]))
            start = {"bloom_level": "applying" if p.get("status") == "passed" else "understanding"}
        context[cid] = {
            "name": step["name"],
            "dimension": step["dimension"],
            "skill_kind": step.get("skill_kind"),
            "baseline": results[cid]["score"],
            "after_training": p.get("current", results[cid]["score"]),
            "training_status": p.get("status"),
            "activity_types": p.get("activity_types", []),
            "training_artifacts": [lv["artifact_title"] for a in activities for lv in a.levels],
            "behavior": behavior,
            **start,
        }

    child = Assessment(
        trainee=assessment.trainee,
        kind="reassessment",
        parent_pk=assessment.id,
        status="created" if skill_blueprint else "skill_done",
        skill_blueprint=skill_blueprint,
        knowledge_blueprint=knowledge_blueprint,
        skill_results=[] if not skill_blueprint else None,
        adaptation_summary="إعادة القياس تتحقق من فجوات رحلتك التعليمية بمواقف جديدة لم ترها من قبل.",
        reassessment_context={"parent_assessment_id": assessment.assessment_id, "competencies": context},
    )
    db.add(child)
    db.flush()
    child.assessment_id = f"AS-{child.id:04d}"
    db.commit()
    return child


# ---------------------------------------------------------------------------
# Steering the questions
# ---------------------------------------------------------------------------

_SIGNAL_GUIDANCE = {
    "weak_justification": "The trainee detects problems but justifies weakly: make the correct answer hinge on the REASON — distractors should be the right action for the wrong reason.",
    "hint_reliance": "The trainee relied on hints during training: give no scaffolding in the question; it must be answered independently.",
    "repeated_error": "The trainee repeatedly missed this error type: {value}. Include that concept in a new form.",
    "improving": "The trainee improved during training: test transfer with a clearly different, slightly more demanding situation.",
    "many_attempts": "The trainee made many wrong attempts: make the situation precise so a correct answer reflects understanding, not elimination.",
    "unusual_time": "The trainee took unusually long: keep the question especially clear and short.",
}


def question_context(assessment: Assessment, competency_id: str) -> str:
    """Text for the question prompt's reassessment section."""
    ctx = (assessment.reassessment_context or {}).get("competencies", {}).get(competency_id)
    if not ctx:
        return "(not a reassessment)"
    lines = [
        "This is a REASSESSMENT after the trainee's learning journey on this competency.",
        f"- Score before training: {ctx['baseline']}%; estimated after training: {ctx['after_training']}%.",
        f"- Training activities used: {', '.join(ctx['activity_types']) or 'none'}.",
        "- Write a NEW situation: different context, artifact and wording from the original assessment questions AND from the training artifacts "
        f"({'; '.join(ctx['training_artifacts'][:8]) or 'none'}). It verifies transfer of learning, not memory of the training content.",
    ]
    for signal in ctx["behavior"].get("signals", []):
        guidance = _SIGNAL_GUIDANCE.get(signal["id"])
        if guidance:
            lines.append("- " + guidance.format(value=signal["value"]))
    return "\n".join(lines)


def starting_points(assessment: Assessment) -> tuple[dict[str, int], dict[str, str]]:
    comps = (assessment.reassessment_context or {}).get("competencies", {})
    difficulty = {cid: c["difficulty"] for cid, c in comps.items() if "difficulty" in c}
    bloom = {cid: c["bloom_level"] for cid, c in comps.items() if "bloom_level" in c}
    return difficulty, bloom


def parent_question_texts(assessment: Assessment) -> list[str]:
    return [q.question_text for q in assessment.parent.questions] if assessment.parent else []


# ---------------------------------------------------------------------------
# The new report
# ---------------------------------------------------------------------------

def _decide(after: float, before: float, status: str) -> str:
    if status == "insufficient_evidence":
        return "insufficient"
    if after >= TARGET_SCORE:
        return "closed"
    if after - before >= PARTIAL_GAIN:
        return "partial"
    return "persistent"


def build_reassessment_report(assessment: Assessment, skill_results: list[dict], knowledge_results: list[dict]) -> dict:
    report = build_report(assessment, skill_results, knowledge_results)
    comps = assessment.reassessment_context["competencies"]
    results = {r["competency_id"]: r for r in skill_results + knowledge_results}

    comparison, new_gaps, journey = [], [], []
    for cid, ctx in comps.items():
        r = results[cid]
        decision = _decide(r["score"], ctx["baseline"], r["status"])
        title, message = DECISIONS[decision]
        tried = len(ctx["activity_types"])
        human = decision == "persistent" and tried >= HUMAN_SUPPORT_AFTER
        if human:
            message += " جرّبنا أكثر من نشاط؛ يُقترح تدخل بشري (مرشد أو مدرب)."
        signals = ctx["behavior"].get("signals", [])
        comparison.append({
            "competency_id": cid,
            "name": ctx["name"],
            "dimension": ctx["dimension"],
            "skill_kind": ctx["skill_kind"],
            "before": ctx["baseline"],
            "after_training": ctx["after_training"],
            "after": r["score"],
            "target_score": TARGET_SCORE,
            "decision": decision,
            "decision_title": title,
            "decision_message": message,
            "needs_human": human,
            "behavior": signals,
        })

        metrics = ctx["behavior"].get("metrics", {})
        if decision == "closed" and any(s["id"] == "weak_justification" for s in signals):
            gap = {
                "competency_id": f"{cid}J"[:10],
                "name": f"تبرير الحل في «{ctx['name']}»",
                "description": f"شرح سبب الخطأ وسبب الإصلاح في {ctx['name']}، لا اكتشافه فقط.",
                "dimension": "knowledge",
                "skill_kind": None,
                "importance": 2,
                "related_skill_ids": [cid] if ctx["dimension"] == "skill" else [],
                "score": round(100 * (metrics.get("explanation_rate") or 0), 1),
                "target_score": TARGET_SCORE,
                "status": "potential_gap",
                "status_label": STATUS_LABELS["potential_gap"],
                "evidence": [],
                "question_count": 0,
                "question_types": [],
                "low_confidence_count": 0,
                "origin": "ظهرت أثناء التدريب: يكتشف الخطأ بدقة لكن تبريره أضعف.",
            }
            new_gaps.append(gap)

        if decision in ("partial", "persistent", "insufficient"):
            order = choose_activities(r, [e["question_type"] for e in r["evidence"] if e["result_percent"] < 50])
            if decision == "persistent":  # change the learning method: untried activities first
                order = [a for a in order if a not in ctx["activity_types"]] + [a for a in order if a in ctx["activity_types"]]
            journey.append(_step(len(journey) + 1, r, order))

    for gap in new_gaps:
        journey.append(_step(len(journey) + 1, gap, choose_activities(gap, [])))

    report.update({
        "kind": "reassessment",
        "parent_assessment_id": assessment.reassessment_context["parent_assessment_id"],
        "comparison": comparison,
        "new_gaps": new_gaps,
        "learning_journey": journey,
    })
    return report


def _step(number: int, result: dict, order: list[str]) -> dict:
    return {
        "step": number,
        "competency_id": result["competency_id"],
        "name": result["name"],
        "dimension": result["dimension"],
        "skill_kind": result.get("skill_kind") if result["dimension"] == "skill" else None,
        "baseline_score": result["score"],
        "activity": activity_card(order[0]),
        "alternatives": [activity_card(a) for a in order[1:]],
    }
