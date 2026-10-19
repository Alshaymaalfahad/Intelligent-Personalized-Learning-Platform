"""صياد الفجوات (Gap Hunter): find the hidden mistakes in a work artifact.

Levels 1–3 get harder (or easier) with performance; level 4 is the boss: a new
situation with no hints. Points: finding a mistake 10, right category +5,
right explanation +5, right fix +10. A false alarm costs 5 and a hint costs 5,
but XP never drops below zero and nothing ends the game.
"""

import copy
import json
import random

from sqlalchemy.orm import Session

from .assessment_engine import EngineError
from .learning_activities import activity_card
from .behavior import activity_behavior, record_event
from .learning_engine import check_available, gap_context, journey_step, record_result
from .models import Assessment, LearningActivity, utcnow
from .question_generator import generate_validated, render_prompt
from .schemas import HuntFirstLevelOutput, HuntLevel, HuntNextLevelOutput

TOTAL_LEVELS = 4  # 3 levels + boss
BOSS_LEVEL = TOTAL_LEVELS
ERRORS_PER_LEVEL = {1: 3, 2: 4, 3: 5, 4: 4}

POINTS_FOUND = 10
POINTS_CATEGORY = 5
POINTS_EXPLANATION = 5
POINTS_FIX = 10
MAX_PER_ERROR = POINTS_FOUND + POINTS_CATEGORY + POINTS_EXPLANATION + POINTS_FIX
FALSE_ALARM_COST = 5
HINT_COST = 5

LINES_RANGE = (8, 16)
MAX_LINE_CHARS = 160
CATEGORIES_RANGE = (4, 6)

BADGES = {
    "hawk_eye": ("🦅", "عين الصقر", "اكتشفت كل أخطاء مرحلة دون أي تلميح."),
    "zero_false_alarms": ("🎯", "صفر إنذارات كاذبة", "لم تحدد أي سطر سليم كخطأ طوال النشاط."),
    "boss_slayer": ("👑", "قاهر الزعيم", "اصطدت كل أخطاء مرحلة الزعيم."),
    "ready": ("🏅", "جاهز للتحقق", "اجتزت مرحلة الزعيم؛ تُثبت إعادة القياس إغلاق الفجوة."),
}
RANKS = [(80, "صياد خبير"), (50, "صياد محترف"), (0, "صياد مبتدئ")]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def validate_level(level: HuntLevel, error_count: int) -> list[str]:
    problems = []
    n = len(level.lines)
    if not LINES_RANGE[0] <= n <= LINES_RANGE[1]:
        problems.append(f"lines must be {LINES_RANGE[0]}-{LINES_RANGE[1]}, got {n}.")
    if any(not line.strip() or len(line) > MAX_LINE_CHARS for line in level.lines):
        problems.append(f"every line must be non-empty and under {MAX_LINE_CHARS} characters.")
    if not level.artifact_title.strip() or not level.mentor_message.strip():
        problems.append("artifact_title and mentor_message are required.")
    cats = [c.strip() for c in level.categories]
    if not CATEGORIES_RANGE[0] <= len(cats) <= CATEGORIES_RANGE[1] or len(set(cats)) != len(cats) or not all(cats):
        problems.append(f"categories must be {CATEGORIES_RANGE[0]}-{CATEGORIES_RANGE[1]} distinct names.")
    if len(level.errors) != error_count:
        problems.append(f"exactly {error_count} errors are required, got {len(level.errors)}.")
    seen = set()
    first_allowed = 1 if level.artifact_kind == "table" else 0
    for i, e in enumerate(level.errors):
        label = f"errors[{i}]"
        for line in [e.line_index, *e.related_lines]:
            if not first_allowed <= line < n:
                problems.append(f"{label}: line {line} is out of range (header line cannot hold an error).")
            if line in seen:
                problems.append(f"{label}: only one error per line (including related_lines).")
            seen.add(line)
        if e.category.strip() not in cats:
            problems.append(f"{label}: category must be one of the categories.")
        for name, options, correct in (
            ("explanation", e.explanation_options, e.correct_explanation),
            ("fix", e.fix_options, e.correct_fix),
        ):
            if len(options) != 3 or len({o.strip() for o in options}) != 3 or not all(o.strip() for o in options):
                problems.append(f"{label}: {name}_options needs 3 distinct options.")
            if not 0 <= correct < len(options):
                problems.append(f"{label}: correct_{name} is out of range.")
        if not e.hint_1.strip() or not e.hint_2.strip():
            problems.append(f"{label}: both hints are required.")
    if len(level.line_notes) != n:
        problems.append(f"line_notes must have exactly one item per line ({n}).")
    used = {e.category.strip() for e in level.errors}
    if len(used) == len(cats):
        problems.append("include at least one category that no error uses (a plausible distractor).")
    return problems


def _shuffle_correct(options: list[str], correct: int) -> tuple[list[str], int]:
    options = [o.strip() for o in options]
    target = random.randrange(len(options))
    options[correct], options[target] = options[target], options[correct]
    return options, target


def _store_level(level: HuntLevel, number: int, difficulty: int) -> dict:
    errors = []
    for e in sorted(level.errors, key=lambda e: e.line_index):
        explanations, correct_explanation = _shuffle_correct(e.explanation_options, e.correct_explanation)
        fixes, correct_fix = _shuffle_correct(e.fix_options, e.correct_fix)
        errors.append({
            "line_index": e.line_index,
            "related_lines": sorted(set(e.related_lines) - {e.line_index}),
            "category": e.category.strip(),
            "explanation_options": explanations,
            "correct_explanation": correct_explanation,
            "fix_options": fixes,
            "correct_fix": correct_fix,
            "hints": [e.hint_1.strip(), e.hint_2.strip()],
            "hints_shown": 0,
            "found": False,
            "justified": False,
            "revealed": False,
        })
    return {
        "number": number,
        "is_boss": number == BOSS_LEVEL,
        "difficulty": difficulty,
        "mentor_message": level.mentor_message.strip(),
        "artifact_title": level.artifact_title.strip(),
        "artifact_kind": level.artifact_kind,
        "lines": [line.rstrip() for line in level.lines],
        "line_notes": [note.strip() for note in level.line_notes],
        "categories": [c.strip() for c in level.categories],
        "errors": errors,
        "false_alarm_lines": [],
        "xp": 0,
        "hints_used": 0,
        "finished": False,
        "started_at": utcnow().isoformat(),
    }


def _level_summary(level: dict) -> dict:
    errors = level["errors"]
    return {
        "number": level["number"],
        "is_boss": level["is_boss"],
        "artifact_title": level["artifact_title"],
        "difficulty": level["difficulty"],
        "found": sum(e["found"] for e in errors),
        "total": len(errors),
        "false_alarms": len(level["false_alarm_lines"]),
        "hints_used": level["hints_used"],
        "xp": level["xp"],
        "max_xp": len(errors) * MAX_PER_ERROR,
    }


def _generate_level(assessment: Assessment, activity: LearningActivity, number: int, difficulty: int) -> tuple[dict | None, dict]:
    ctx = gap_context(assessment, activity.competency_id)
    first = number == 1
    if first:
        mission_block = (
            "# Mission card (level 1 only)\n\n"
            "Also write the mission card shown before the game starts: `title` (short and catchy), "
            "`story` (2–3 short Arabic sentences setting a realistic work situation with a little urgency, "
            "e.g. a report must reach a client today), `goal` (one sentence), and `win_condition` "
            "(one sentence, e.g. اصطد كل الأخطاء قبل أن يصل التقرير للعميل). Level 1 continues this story."
        )
    else:
        mission_block = f"# Mission (for continuity — keep the same story world)\n\n{json.dumps(activity.mission, ensure_ascii=False)}"
    role = (
        "This is the BOSS level: a NEW situation the trainee has not seen in earlier levels (a different artifact type or context), "
        "used to verify mastery. No hints will be shown, but still write them."
        if number == BOSS_LEVEL
        else "A regular level; each level's mistakes are smarter and better hidden than the previous one's (unless the difficulty says otherwise)."
    )
    previous = [
        {**_level_summary(lv), "mistakes": [{"category": e["category"], "found": e["found"]} for e in lv["errors"]]}
        for lv in activity.levels
    ]
    prompt = render_prompt(
        "gap_hunter_level.txt",
        specialization=assessment.trainee.specialization,
        competency=json.dumps(ctx["competency"], ensure_ascii=False),
        gap_evidence=json.dumps(ctx["evidence"], ensure_ascii=False, indent=2) if ctx["evidence"] else "(no wrong answers recorded — evidence was limited)",
        level_number=number,
        total_levels=TOTAL_LEVELS,
        level_role=role,
        difficulty=difficulty,
        error_count=ERRORS_PER_LEVEL[number],
        previous_levels=json.dumps(previous, ensure_ascii=False, indent=2) if previous else "(none — this is the first level)",
        mission_block=mission_block,
    )
    count = ERRORS_PER_LEVEL[number]
    if first:
        out = generate_validated(
            prompt, HuntFirstLevelOutput,
            lambda o: validate_level(o.level, count) + (["mission fields are required."] if not all(
                getattr(o.mission, f).strip() for f in ("title", "story", "goal", "win_condition")) else []),
            task="gap_hunter_level_1",
        )
        return out.mission.model_dump(), _store_level(out.level, number, difficulty)
    out = generate_validated(
        prompt, HuntNextLevelOutput, lambda o: validate_level(o.level, count), task=f"gap_hunter_level_{number}"
    )
    return None, _store_level(out.level, number, difficulty)


def _next_difficulty(level: dict) -> tuple[int, str]:
    s = _level_summary(level)
    performance = s["xp"] / s["max_xp"] if s["max_xp"] else 0
    if performance >= 0.8 and s["hints_used"] <= 1:
        return min(5, level["difficulty"] + 1), "up"
    if performance < 0.5:
        return max(1, level["difficulty"] - 1), "down"
    return level["difficulty"], "same"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def start(db: Session, assessment: Assessment, competency_id: str) -> LearningActivity:
    check_available("gap_hunter")
    if assessment.status != "completed":
        raise EngineError(409, "أكمل التقييم أولًا.")
    journey_step(assessment, competency_id)
    existing = next(
        (a for a in assessment.activities
         if a.competency_id == competency_id and a.activity_type == "gap_hunter" and a.status != "completed"),
        None,
    )
    if existing:
        return existing

    ctx = gap_context(assessment, competency_id)
    difficulty = min(5, (2 if ctx["status"] == "likely_gap" else 3) + ctx["rounds_played"])
    activity = LearningActivity(
        assessment=assessment, competency_id=competency_id, activity_type="gap_hunter", status="generating", levels=[], badges=[]
    )
    db.add(activity)
    db.flush()
    activity.activity_id = f"LA-{activity.id:04d}"
    db.commit()
    try:
        mission, level = _generate_level(assessment, activity, 1, difficulty)
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


def _current(activity: LearningActivity) -> dict:
    if activity.status != "playing":
        raise EngineError(409, "لا توجد مرحلة نشطة الآن.")
    return activity.levels[-1]


def _save(activity: LearningActivity, levels: list, xp_change: int) -> None:
    activity.levels = levels  # reassign so the JSON column is marked as changed
    activity.xp = max(0, activity.xp + xp_change)


def _covers(error: dict, line_index: int) -> bool:
    return line_index == error["line_index"] or line_index in error["related_lines"]


def mark(db: Session, activity: LearningActivity, line_index: int, category: str) -> dict:
    levels = copy.deepcopy(activity.levels)
    level = levels[-1]
    _current(activity)
    if not 0 <= line_index < len(level["lines"]) or (level["artifact_kind"] == "table" and line_index == 0):
        raise EngineError(422, "اختر سطرًا من المحتوى.")
    if category not in level["categories"]:
        raise EngineError(422, "اختر تصنيفًا من القائمة.")
    if line_index in level["false_alarm_lines"] or any(_covers(e, line_index) and e["found"] for e in level["errors"]):
        raise EngineError(409, "سبق أن فحصت هذا السطر.")

    error = next((e for e in level["errors"] if _covers(e, line_index) and not e["revealed"]), None)
    if error is None:
        level["false_alarm_lines"].append(line_index)
        level["xp"] -= FALSE_ALARM_COST
        activity.false_alarms += 1
        _save(activity, levels, -FALSE_ALARM_COST)
        record_event(db, activity, level, "false_alarm", correct=False, details={"line": line_index, "category": category})
        db.commit()
        note = level.get("line_notes", [""] * len(level["lines"]))[line_index]
        return {"result": "false_alarm", "xp_change": -FALSE_ALARM_COST, "why_correct": note}

    error["found"] = True
    error["category_ok"] = category == error["category"]
    gained = POINTS_FOUND + (POINTS_CATEGORY if error["category_ok"] else 0)
    level["xp"] += gained
    _save(activity, levels, gained)
    record_event(db, activity, level, "mark_found", correct=True, category=error["category"],
                 details={"line": error["line_index"], "chosen_category": category, "category_ok": error["category_ok"]})
    db.commit()
    return {
        "result": "found",
        "line_index": error["line_index"],
        "xp_change": gained,
        "category_ok": error["category_ok"],
        "correct_category": error["category"],
        "explanation_options": error["explanation_options"],
        "fix_options": error["fix_options"],
    }


def justify(db: Session, activity: LearningActivity, line_index: int, explanation: int, fix: int) -> dict:
    levels = copy.deepcopy(activity.levels)
    level = levels[-1]
    _current(activity)
    error = next((e for e in level["errors"] if _covers(e, line_index) and e["found"]), None)
    if error is None:
        raise EngineError(409, "اصطد الخطأ أولًا.")
    if error["justified"]:
        raise EngineError(409, "سبق أن برّرت هذا الخطأ.")
    if not 0 <= explanation < len(error["explanation_options"]) or not 0 <= fix < len(error["fix_options"]):
        raise EngineError(422, "اختيار غير صالح.")
    error["justified"] = True
    error["explanation_ok"] = explanation == error["correct_explanation"]
    error["fix_ok"] = fix == error["correct_fix"]
    gained = (POINTS_EXPLANATION if error["explanation_ok"] else 0) + (POINTS_FIX if error["fix_ok"] else 0)
    level["xp"] += gained
    _save(activity, levels, gained)
    record_event(db, activity, level, "justify", correct=error["explanation_ok"] and error["fix_ok"], category=error["category"],
                 details={"line": error["line_index"], "explanation_ok": error["explanation_ok"], "fix_ok": error["fix_ok"]})
    db.commit()
    return {
        "xp_change": gained,
        "explanation_ok": error["explanation_ok"],
        "fix_ok": error["fix_ok"],
        "correct_explanation": error["correct_explanation"],
        "correct_fix": error["correct_fix"],
    }


def hint(db: Session, activity: LearningActivity) -> dict:
    levels = copy.deepcopy(activity.levels)
    level = levels[-1]
    _current(activity)
    if level["is_boss"]:
        raise EngineError(409, "لا توجد تلميحات في مرحلة الزعيم.")
    error = next((e for e in level["errors"] if not e["found"] and e["hints_shown"] < 2), None)
    if error is None:
        raise EngineError(409, "لا توجد تلميحات أخرى في هذه المرحلة.")
    text = error["hints"][error["hints_shown"]]
    error["hints_shown"] += 1
    level["hints_used"] += 1
    level["xp"] -= HINT_COST
    activity.hints_used += 1
    _save(activity, levels, -HINT_COST)
    record_event(db, activity, level, "hint", category=error["category"], details={"hint_level": error["hints_shown"]})
    db.commit()
    return {"hint": text, "xp_change": -HINT_COST}


def _award(activity: LearningActivity, badge: str) -> None:
    if badge not in activity.badges:
        activity.badges = activity.badges + [badge]


def finish_level(db: Session, assessment: Assessment, activity: LearningActivity) -> None:
    """Close the level (revealing any missed mistakes) and prepare the next one or the result."""
    levels = copy.deepcopy(activity.levels)
    level = levels[-1]
    _current(activity)
    for e in level["errors"]:
        if not e["found"]:
            e["revealed"] = True
    level["finished"] = True
    if all(e["found"] for e in level["errors"]) and level["hints_used"] == 0:
        _award(activity, "boss_slayer" if level["is_boss"] else "hawk_eye")
    activity.levels = levels
    activity.status = "generating"
    db.commit()

    if level["number"] < TOTAL_LEVELS:
        difficulty, direction = _next_difficulty(level)
        decision = {"up": "next_level_harder", "down": "next_level_easier", "same": "next_level_same"}[direction]
        record_event(db, activity, level, "finish_level", details=_level_summary(level), decision=decision)
        try:
            _, new_level = _generate_level(assessment, activity, level["number"] + 1, difficulty)
        except Exception:
            db.rollback()  # drop the finish_level event; the level is reopened below
            levels[-1]["finished"] = False  # let the trainee retry finishing the level
            for e in levels[-1]["errors"]:
                if not e["found"]:
                    e["revealed"] = False
            activity.levels = levels
            activity.status = "playing"
            db.commit()
            raise
        activity.levels = levels + [new_level]
        activity.current_level = new_level["number"]
        activity.status = "playing"
        db.commit()
        return

    boss = _level_summary(level)
    boss_percent = 100 * max(0, boss["xp"]) / boss["max_xp"]
    outcome = record_result(assessment, activity, boss_percent)
    record_event(db, activity, level, "finish_level", details=boss, decision=f"gap_{outcome['decision']}")
    outcome["behavior"] = activity_behavior(db, activity)["signals"]
    if activity.false_alarms == 0:
        _award(activity, "zero_false_alarms")
    if outcome["decision"] == "passed":
        _award(activity, "ready")
    total_max = sum(len(lv["errors"]) for lv in levels) * MAX_PER_ERROR
    percent = 100 * activity.xp / total_max if total_max else 0
    outcome["rank"] = next(name for threshold, name in RANKS if percent >= threshold)
    outcome["xp"] = activity.xp
    outcome["max_xp"] = total_max
    activity.result = outcome
    activity.status = "completed"
    db.commit()


# ---------------------------------------------------------------------------
# View — never includes the answer key of mistakes that are still hidden
# ---------------------------------------------------------------------------

def _public_error(e: dict) -> dict:
    item = {"line_index": e["line_index"], "related_lines": e["related_lines"], "found": e["found"], "revealed": e["revealed"]}
    if e["found"]:
        item.update({
            "category_ok": e.get("category_ok"),
            "correct_category": e["category"],
            "explanation_options": e["explanation_options"],
            "fix_options": e["fix_options"],
            "justified": e["justified"],
        })
        if e["justified"]:
            item.update({
                "explanation_ok": e["explanation_ok"], "fix_ok": e["fix_ok"],
                "correct_explanation": e["correct_explanation"], "correct_fix": e["correct_fix"],
            })
    if e["revealed"]:
        item.update({
            "correct_category": e["category"],
            "explanation": e["explanation_options"][e["correct_explanation"]],
            "fix": e["fix_options"][e["correct_fix"]],
        })
    return item


def _public_level(level: dict) -> dict:
    visible_hints = [h for e in level["errors"] for h in e["hints"][: e["hints_shown"]]]
    return {
        **_level_summary(level),
        "mentor_message": level["mentor_message"],
        "artifact_kind": level["artifact_kind"],
        "lines": level["lines"],
        "categories": level["categories"],
        "false_alarm_lines": level["false_alarm_lines"],
        "errors": [_public_error(e) for e in level["errors"] if e["found"] or e["revealed"]],
        "hints": visible_hints,
        "can_hint": not level["is_boss"] and any(not e["found"] and e["hints_shown"] < 2 for e in level["errors"]),
        "finished": level["finished"],
    }


def view(activity: LearningActivity) -> dict:
    assessment = activity.assessment
    step = journey_step(assessment, activity.competency_id)
    return {
        "activity_id": activity.activity_id,
        "assessment_id": assessment.assessment_id,
        "competency_id": activity.competency_id,
        "competency_name": step["name"],
        "activity": activity_card(activity.activity_type),
        "status": activity.status,
        "mission": activity.mission,
        "total_levels": TOTAL_LEVELS,
        "current_level": activity.current_level,
        "xp": activity.xp,
        "hints_used": activity.hints_used,
        "false_alarms": activity.false_alarms,
        "rules": {
            "found": POINTS_FOUND, "category": POINTS_CATEGORY, "explanation": POINTS_EXPLANATION,
            "fix": POINTS_FIX, "false_alarm": FALSE_ALARM_COST, "hint": HINT_COST,
        },
        "badges": [{"id": b, "icon": BADGES[b][0], "name": BADGES[b][1], "description": BADGES[b][2]} for b in activity.badges],
        "levels": [_public_level(lv) for lv in activity.levels],
        "result": activity.result,
    }
