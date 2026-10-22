"""Shared game engine for the learning activities (escape room, work challenge,
shadow, teach others). Gap Hunter predates it and keeps its own module.

Each activity module provides:
    TOTAL_LEVELS                   levels including the boss (the last one)
    PROMPT, FIRST_OUTPUT, NEXT_OUTPUT, MISSION_FIELDS
    validate(output_level, number, is_boss) -> list[str]
    build_level(output_level, number, is_boss) -> dict   content + state + hints + max_xp
    public(level) -> dict                                 what the browser may see
    act(db, activity, level, action, payload) -> dict     mutates level; returns outcome with "xp_change"
    reveal(level)                                         on finishing a level early
    notes(level) -> dict                                  short summary for the next level's prompt
    extra_badges(activity, level) -> list[str]

The core handles levels, XP (never below zero), hint coins, difficulty adaptation,
the boss, badges, behavior events, and the end-of-activity decision.
"""

import copy
import importlib
import json

from sqlalchemy.orm import Session

from .assessment_engine import EngineError
from .behavior import activity_behavior, record_event
from .i18n import lang_of
from .learning_activities import activity_card
from .learning_engine import check_available, gap_context, journey_step, record_result
from .models import Assessment, LearningActivity, public_id, utcnow
from .question_generator import generate_validated, render_prompt

MODULES = {
    "escape_room": "backend.escape_room",
    "work_challenge": "backend.work_challenge",
    "shadow": "backend.shadow",
    "teach_others": "backend.teach_others",
}
HINT_COST = 5

BADGE_ICONS = {
    "independent": "🧭", "boss_slayer": "👑", "ready": "🏅", "escape_artist": "🗝️", "client_star": "⭐",
    "expert_shadow": "🥷", "golden_collector": "🃏", "inspiring_teacher": "🎓",
}  # names and descriptions are translated by the frontend


def module(activity_type: str):
    return importlib.import_module(MODULES[activity_type])


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _summary(level: dict) -> dict:
    return {
        "number": level["number"],
        "is_boss": level["is_boss"],
        "title": level["title"],
        "difficulty": level["difficulty"],
        "xp": level["xp"],
        "max_xp": level["max_xp"],
        "hints_used": level["hints_used"],
        "percent": round(100 * max(0, level["xp"]) / level["max_xp"]) if level["max_xp"] else 0,
    }


def _generate(assessment: Assessment, activity: LearningActivity, number: int, difficulty: int) -> tuple[dict | None, dict]:
    mod = module(activity.activity_type)
    ctx = gap_context(assessment, activity.competency_id)
    first = number == 1
    is_boss = number == mod.TOTAL_LEVELS
    if first:
        mission_block = (
            "# Mission card (level 1 only)\n\nAlso write the mission card shown before the game starts: "
            f"{mod.MISSION_FIELDS} Level 1 continues this story."
        )
    else:
        mission_block = f"# Mission (keep the same story world)\n\n{json.dumps(activity.mission, ensure_ascii=False)}"
    role = (
        "This is the BOSS level: a NEW situation the trainee has not seen in earlier levels, used to verify mastery. "
        "No hints or help will be shown to the trainee."
        if is_boss
        else "A regular level. Adapt to how the trainee did in previous levels."
    )
    previous = [{**_summary(lv), **mod.notes(lv)} for lv in activity.levels]
    prompt = render_prompt(
        mod.PROMPT,
        lang=lang_of(assessment.trainee),
        specialization=assessment.trainee.specialization,
        competency=json.dumps(ctx["competency"], ensure_ascii=False),
        gap_evidence=json.dumps(ctx["evidence"], ensure_ascii=False, indent=2) if ctx["evidence"] else "(no wrong answers recorded — evidence was limited)",
        level_number=number,
        total_levels=mod.TOTAL_LEVELS,
        level_role=role,
        difficulty=difficulty,
        previous_levels=json.dumps(previous, ensure_ascii=False, indent=2) if previous else "(none — this is the first level)",
        mission_block=mission_block,
    )

    def validate(out) -> list[str]:
        problems = mod.validate(_level_of(out), number, is_boss)
        if first:
            problems += [f"mission.{f} is required." for f, v in out.mission.model_dump().items() if not str(v).strip()]
        return problems

    output = generate_validated(
        prompt, mod.FIRST_OUTPUT if first else mod.NEXT_OUTPUT, validate, task=f"{activity.activity_type}_level_{number}"
    )
    level = mod.build_level(_level_of(output), number, is_boss)
    level.update({
        "number": number,
        "is_boss": is_boss,
        "difficulty": difficulty,
        "xp": 0,
        "hints_shown": 0,
        "hints_used": 0,
        "finished": False,
        "started_at": utcnow().isoformat(),
    })
    if is_boss:
        level["hints"] = []
    return (output.mission.model_dump() if first else None), level


def _level_of(output):
    for name in ("door", "task", "level"):
        if hasattr(output, name):
            return getattr(output, name)
    raise AttributeError("activity output has no level")


def _next_difficulty(level: dict) -> int:
    s = _summary(level)
    if s["percent"] >= 80 and s["hints_used"] <= 1:
        return min(5, level["difficulty"] + 1)
    if s["percent"] < 50:
        return max(1, level["difficulty"] - 1)
    return level["difficulty"]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def start(db: Session, assessment: Assessment, competency_id: str, activity_type: str) -> LearningActivity:
    check_available(activity_type)
    if assessment.status != "completed":
        raise EngineError(409, "أكمل التقييم أولًا.")
    journey_step(assessment, competency_id)
    existing = next(
        (a for a in assessment.activities
         if a.competency_id == competency_id and a.activity_type == activity_type and a.status != "completed"),
        None,
    )
    if existing:
        return existing

    ctx = gap_context(assessment, competency_id)
    difficulty = min(5, (2 if ctx["status"] == "likely_gap" else 3) + ctx["rounds_played"])
    activity = LearningActivity(
        assessment=assessment, competency_id=competency_id, activity_type=activity_type,
        status="generating", levels=[], badges=[],
    )
    db.add(activity)
    db.flush()
    activity.activity_id = public_id("LA")
    db.commit()
    try:
        mission, level = _generate(assessment, activity, 1, difficulty)
    except Exception:
        db.delete(activity)
        db.commit()
        raise
    activity.mission = mission
    activity.levels = [level]
    activity.current_level = 1
    activity.status = "playing"
    db.commit()
    return activity


def _playing_level(activity: LearningActivity) -> tuple[list, dict]:
    if activity.status != "playing":
        raise EngineError(409, "لا توجد مرحلة نشطة الآن.")
    levels = copy.deepcopy(activity.levels)
    level = levels[-1]
    if level["finished"]:
        raise EngineError(409, "انتهت هذه المرحلة.")
    return levels, level


def act(db: Session, activity: LearningActivity, action: str, payload: dict) -> dict:
    levels, level = _playing_level(activity)
    mod = module(activity.activity_type)
    outcome = mod.act(db, activity, level, action, payload)
    level["xp"] += outcome.get("xp_change", 0)
    activity.levels = levels  # reassign so the JSON column is marked as changed
    activity.xp = max(0, activity.xp + outcome.get("xp_change", 0))
    for event in outcome.pop("events", []):
        record_event(db, activity, level, event["type"], correct=event.get("correct"),
                     category=event.get("category"), details=event.get("details"))
    db.commit()
    return outcome


def hint(db: Session, activity: LearningActivity) -> dict:
    levels, level = _playing_level(activity)
    if level["is_boss"]:
        raise EngineError(409, "لا توجد تلميحات في مرحلة الزعيم.")
    mod = module(activity.activity_type)
    text = mod.next_hint(level) if hasattr(mod, "next_hint") else None
    if text is None:
        if level["hints_shown"] >= len(level["hints"]):
            raise EngineError(409, "لا توجد تلميحات أخرى في هذه المرحلة.")
        text = level["hints"][level["hints_shown"]]
        level["hints_shown"] += 1
    level.setdefault("shown_hints", []).append(text)
    level["hints_used"] += 1
    level["xp"] -= HINT_COST
    activity.levels = levels
    activity.xp = max(0, activity.xp - HINT_COST)
    activity.hints_used += 1
    record_event(db, activity, level, "hint", details={"hint": text})
    db.commit()
    return {"hint": text, "xp_change": -HINT_COST}


def _award(activity: LearningActivity, badge: str) -> None:
    if badge not in activity.badges:
        activity.badges = activity.badges + [badge]


def finish_level(db: Session, assessment: Assessment, activity: LearningActivity) -> None:
    levels, level = _playing_level(activity)
    mod = module(activity.activity_type)
    mod.reveal(level)
    level["finished"] = True
    summary = _summary(level)
    if summary["hints_used"] == 0 and summary["percent"] >= 80 and not level["is_boss"]:
        _award(activity, "independent")
    if level["is_boss"] and summary["percent"] >= 90:
        _award(activity, "boss_slayer")
    for badge in mod.extra_badges(activity, level):
        _award(activity, badge)
    activity.levels = levels
    activity.status = "generating"
    db.commit()

    if level["number"] < mod.TOTAL_LEVELS:
        difficulty = _next_difficulty(level)
        direction = "harder" if difficulty > level["difficulty"] else "easier" if difficulty < level["difficulty"] else "same"
        record_event(db, activity, level, "finish_level", details=summary, decision=f"next_level_{direction}")
        try:
            _, new_level = _generate(assessment, activity, level["number"] + 1, difficulty)
        except Exception:
            db.rollback()
            db.refresh(activity)
            reopened = copy.deepcopy(activity.levels)
            reopened[-1]["finished"] = False
            activity.levels = reopened
            activity.status = "playing"
            db.commit()
            raise
        activity.levels = levels + [new_level]
        activity.current_level = new_level["number"]
        activity.status = "playing"
        db.commit()
        return

    outcome = record_result(assessment, activity, summary["percent"])
    record_event(db, activity, level, "finish_level", details=summary, decision=f"gap_{outcome['decision']}")
    outcome["behavior"] = activity_behavior(db, activity)["signals"]
    if outcome["decision"] == "passed":
        _award(activity, "ready")
    total_max = sum(lv["max_xp"] for lv in levels)
    percent = 100 * activity.xp / total_max if total_max else 0
    outcome["rank"] = "expert" if percent >= 80 else "mid" if percent >= 50 else "beginner"  # translated per activity
    outcome["xp"] = activity.xp
    outcome["max_xp"] = total_max
    activity.result = outcome
    activity.status = "completed"
    db.commit()


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

def view(activity: LearningActivity) -> dict:
    mod = module(activity.activity_type)
    step = journey_step(activity.assessment, activity.competency_id)
    levels = []
    for lv in activity.levels:
        levels.append({
            **_summary(lv),
            "mentor_message": lv["mentor_message"],
            "finished": lv["finished"],
            "hints": lv.get("shown_hints", []),
            "can_hint": not lv["is_boss"] and not lv["finished"] and (
                mod.can_hint(lv) if hasattr(mod, "can_hint") else lv["hints_shown"] < len(lv["hints"])
            ),
            **mod.public(lv),
        })
    return {
        "activity_id": activity.activity_id,
        "assessment_id": activity.assessment.assessment_id,
        "competency_id": activity.competency_id,
        "competency_name": step["name"],
        "activity": activity_card(activity.activity_type),
        "status": activity.status,
        "mission": activity.mission,
        "total_levels": mod.TOTAL_LEVELS,
        "current_level": activity.current_level,
        "xp": activity.xp,
        "hints_used": activity.hints_used,
        "rules": {"hint": HINT_COST, **getattr(mod, "RULES", {})},
        "badges": [{"id": b, "icon": BADGE_ICONS[b]} for b in activity.badges],
        "levels": levels,
        "result": activity.result,
    }
