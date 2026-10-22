"""The learning journey built from the skills the trainee picked (no placement test).

The journey lives on an Assessment row (kind="journey") so lessons, the five activities
and progress tracking work on it unchanged: its `report` carries one result per picked
skill (the self-rated level is the starting estimate) and the `learning_journey` steps.
At most MAX_ACTIVE skills are active; the rest wait under «later».

The trainee signs up with an ID they choose (their key to come back). Once a journey
starts its skills are locked; a new round of picks opens only when every station is done.
"""

import re


from sqlalchemy import select
from sqlalchemy.orm import Session

from .assessment_engine import EngineError
from .gap_analyzer import TARGET_SCORE
from .learning_activities import ACTIVITIES, activity_card
from .models import Assessment, LearningActivity, Lesson, Trainee, public_id
from .skills_catalog import AXIS_BY_ID, DEFAULT_LEVEL, LEVELS, MAX_ACTIVE, SKILL_BY_ID, lab_order

TRAINEE_ROLE = "AI solutions lab trainee at a digital solutions company"
ACTIVITY_ORDER = list(ACTIVITIES)
# 6–20 Latin letters/digits (plus - _), with at least one letter and one digit.
TRAINEE_ID = re.compile(r"^(?=.*[A-Z])(?=.*[0-9])[A-Z0-9_-]{6,20}$")


def _clean(selections: list) -> list[dict]:
    """Known skills only, once each, in lab order; skills past the active limit move to «later»."""
    by_id: dict[str, dict] = {}
    for s in selections:
        if s.skill_id not in SKILL_BY_ID:
            raise EngineError(422, "مهارة غير معروفة.")
        by_id[s.skill_id] = {"skill_id": s.skill_id, "level": s.level, "later": s.later}
    cleaned, active = [], 0
    for sid in lab_order(list(by_id)):
        item = by_id[sid]
        if not item["later"]:
            active += 1
            item["later"] = active > MAX_ACTIVE
        cleaned.append(item)
    if not any(not s["later"] for s in cleaned):
        raise EngineError(422, "اختر مهارة واحدة على الأقل لرحلتك.")
    return cleaned


def _result(sel: dict, lang: str) -> dict:
    skill = SKILL_BY_ID[sel["skill_id"]]
    level = LEVELS[sel["level"] or DEFAULT_LEVEL]
    return {
        "competency_id": skill["id"],
        "name": skill["name"][lang],
        "description": skill["can_do"][lang],
        "dimension": "skill",
        "skill_kind": skill["kind"],
        "status": level["status"],
        "score": level["score"],
    }


def _step(sel: dict, lang: str) -> dict:
    skill = SKILL_BY_ID[sel["skill_id"]]
    others = [a for a in ACTIVITY_ORDER if a != skill["activity"]]
    return {
        "competency_id": skill["id"],
        "name": skill["name"][lang],
        "dimension": "skill",
        "axis": skill["axis"],
        "stage": AXIS_BY_ID[skill["axis"]]["stage"],
        "minutes": skill["minutes"],
        "level": sel["level"],
        # Nothing is measured yet: progress starts at 0 and comes only from the trainee's own play.
        # (The self-rated level is only a starting estimate for lesson depth and difficulty.)
        "baseline_score": 0,
        "self_rated": True,
        "activity": activity_card(skill["activity"]),
        "alternatives": [activity_card(a) for a in others],
    }


def _apply(journey: Assessment, selections: list[dict]) -> None:
    lang = journey.trainee.language or "en"
    journey.selections = selections
    journey.report = {
        "kind": "journey",
        "trainee_id": journey.trainee.trainee_id,
        "target_score": TARGET_SCORE,
        # every picked skill has a result, so a «later» skill can join the journey any time
        "skill_results": [_result(s, lang) for s in selections],
        "knowledge_results": [],
        "new_gaps": [],
        "learning_journey": [_step(s, lang) for s in selections if not s["later"]],
        "later": [s["skill_id"] for s in selections if s["later"]],
    }


def _normalize_id(raw: str) -> str:
    trainee_id = raw.strip().upper()
    if not TRAINEE_ID.match(trainee_id):
        raise EngineError(422, "المعرّف يجب أن يكون من 6 إلى 20 حرفًا إنجليزيًا ورقمًا، ويحتوي على حرف ورقم على الأقل.")
    return trainee_id


def is_complete(journey: Assessment) -> bool:
    progress = journey.learning_progress or {}
    steps = journey.report["learning_journey"]
    return bool(steps) and all(progress.get(s["competency_id"], {}).get("activities") for s in steps)


def create(db: Session, raw_id: str, new_trainee: bool, language: str, selections: list) -> Assessment:
    """Sign up with a chosen ID (new_trainee) or, for a returning trainee, start the next round."""
    cleaned = _clean(selections)
    trainee_id = _normalize_id(raw_id)
    trainee = db.scalar(select(Trainee).where(Trainee.trainee_id == trainee_id))
    if new_trainee:
        if trainee is not None:
            raise EngineError(409, "هذا المعرّف مستخدم، اختر معرّفًا آخر.")
        trainee = Trainee(trainee_id=trainee_id, language=language, specialization=TRAINEE_ROLE, interests=[], profile_status="completed")
        db.add(trainee)
        db.flush()
    else:
        if trainee is None:
            raise EngineError(404, "لم نجد هذا المعرّف.")
        current = latest_for(trainee)
        if current is not None and not is_complete(current):
            raise EngineError(409, "اختيار المهارات مقفل حتى تنهي محطات رحلتك الحالية.")
        trainee.language = language
    journey = Assessment(trainee=trainee, kind="journey", status="completed", assessment_id=public_id("JR"))
    db.add(journey)
    db.flush()
    _apply(journey, cleaned)
    db.commit()
    return journey


def latest_for(trainee: Trainee) -> Assessment | None:
    journeys = [a for a in trainee.assessments if a.kind == "journey"]
    return max(journeys, key=lambda a: a.id) if journeys else None


def view(db: Session, journey: Assessment, lang: str) -> dict:
    """The journey map: stations in lab order with their state, plus the «later» list."""
    if journey.kind != "journey":
        raise EngineError(404, "هذه ليست رحلة مهارات.")
    progress = journey.learning_progress or {}
    lessons = {row.competency_id: row for row in db.scalars(select(Lesson).where(Lesson.assessment_pk == journey.id))}
    open_acts = {
        a.competency_id: a for a in db.scalars(select(LearningActivity).where(LearningActivity.assessment_pk == journey.id))
        if a.status != "completed"
    }
    stations, current_found = [], False
    for step in journey.report["learning_journey"]:
        cid = step["competency_id"]
        skill = SKILL_BY_ID[cid]
        entry = progress.get(cid, {})
        if entry.get("activities"):
            state = "done"
        elif not current_found:
            state, current_found = "current", True
        else:
            state = "upcoming"
        stations.append({
            "skill_id": cid,
            "name": skill["name"][lang],
            "can_do": skill["can_do"][lang],
            "axis": step["axis"],
            "stage": step["stage"],
            "minutes": step["minutes"],
            "level": step["level"],
            "activity_type": step["activity"]["activity_type"],
            "state": state,
            "started": cid in lessons or cid in open_acts,
            "decision": entry.get("status"),
            "score": entry.get("current", step["baseline_score"]),
        })
    later = [
        {"skill_id": sid, "name": SKILL_BY_ID[sid]["name"][lang], "minutes": SKILL_BY_ID[sid]["minutes"], "axis": SKILL_BY_ID[sid]["axis"]}
        for sid in journey.report.get("later", [])
    ]
    return {
        "journey_id": journey.assessment_id,
        "trainee_id": journey.trainee.trainee_id,
        "selections": journey.selections or [],
        "stations": stations,
        "later": later,
        "done": sum(s["state"] == "done" for s in stations),
        "complete": is_complete(journey),
        "total_minutes": sum(s["minutes"] for s in stations),
    }


def localize_steps(report: dict, lang: str) -> dict:
    """Step names follow the page language (they were stored in the trainee's language)."""
    if report.get("kind") != "journey":
        return report
    steps = [{**s, "name": SKILL_BY_ID[s["competency_id"]]["name"][lang]} for s in report["learning_journey"]]
    return {**report, "learning_journey": steps}
