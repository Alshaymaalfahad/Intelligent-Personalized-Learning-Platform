"""👥 الظل والظل العكسي (Shadow / reverse shadow).

Level 1 — shadow: the trainee watches an expert solve a work problem step by step.
At pause points the expert asks «وش تتوقع خطوتي الجاية؟»; a right prediction earns
points and a «golden practice» card.

Level 2 — reverse shadow: on a similar task the trainee builds their own sequence
from step cards (some are traps); the expert's steps are then shown side by side
with a match percentage and the steps that were missed.

Level 3 — boss: reverse shadow on a new situation, no hints.
"""

import random

from .activity_schemas import ShadowFirstOutput, ShadowNextOutput
from .assessment_engine import EngineError

TOTAL_LEVELS = 3
PROMPT = "shadow_level.txt"
FIRST_OUTPUT = ShadowFirstOutput
NEXT_OUTPUT = ShadowNextOutput
MISSION_FIELDS = (
    "`title`, `story` (2–3 short Arabic sentences introducing the expert and the situation), `goal`, `win_condition`, "
    "and `expert_name` (Arabic name and role, e.g. «م. خالد — مهندس برمجيات أول»)."
)
RULES = {"predict": 10, "match": 40}
PREDICT_POINTS = 10
DO_MAX_XP = 40
STEPS_RANGE = (5, 7)
PAUSES = 3


def mode_of(number: int) -> str:
    return "watch" if number == 1 else "do"


def validate(lv, number: int, is_boss: bool) -> list[str]:
    p = []
    steps = lv.expert_steps
    if not STEPS_RANGE[0] <= len(steps) <= STEPS_RANGE[1]:
        p.append(f"expert_steps must have {STEPS_RANGE[0]}-{STEPS_RANGE[1]} steps.")
    if any(not s.step.strip() or len(s.step) > 160 or not s.why.strip() or not s.golden_practice.strip() for s in steps):
        p.append("each expert step needs step (under 160 characters), why and golden_practice.")
    if len({s.step.strip() for s in steps}) != len(steps):
        p.append("expert steps must be distinct.")
    if not lv.situation.strip() or len(lv.situation) > 700:
        p.append("situation is required and must be under 700 characters.")
    if len(lv.artifact_lines) > 12 or any(len(x) > 160 for x in lv.artifact_lines):
        p.append("artifact_lines: at most 12 lines, each under 160 characters.")
    if mode_of(number) == "watch":
        idx = [x.step_index for x in lv.pauses]
        if len(lv.pauses) != PAUSES or len(set(idx)) != PAUSES or any(not 1 <= i < len(steps) for i in idx):
            p.append(f"exactly {PAUSES} pauses with distinct step_index between 1 and {len(steps) - 1}.")
        for x in lv.pauses:
            if len(x.distractors) != 2 or not all(d.strip() for d in x.distractors) or not x.hint.strip():
                p.append("each pause needs 2 distractors and a hint.")
                break
    distractors = [d.strip() for d in lv.distractor_steps]
    if len(distractors) != 3 or not all(distractors) or set(distractors) & {s.step.strip() for s in steps}:
        p.append("distractor_steps must be 3 plausible steps that are not expert steps.")
    if not is_boss and mode_of(number) == "do" and (len(lv.hints) != 2 or not all(h.strip() for h in lv.hints)):
        p.append("exactly 2 hints are required.")
    return p


def build_level(lv, number: int, is_boss: bool) -> dict:
    mode = mode_of(number)
    steps = [{"step": s.step.strip(), "why": s.why.strip(), "golden": s.golden_practice.strip()} for s in lv.expert_steps]
    pauses = []
    for x in sorted(lv.pauses, key=lambda x: x.step_index) if mode == "watch" else []:
        options = [steps[x.step_index]["step"]] + [d.strip() for d in x.distractors]
        order = list(range(3))
        random.shuffle(order)
        pauses.append({"step_index": x.step_index, "options": [options[i] for i in order], "correct": order.index(0), "hint": x.hint.strip()})
    pool = [{"text": s["step"], "expert_index": i} for i, s in enumerate(steps)] + [
        {"text": d.strip(), "expert_index": None} for d in lv.distractor_steps
    ]
    random.shuffle(pool)
    return {
        "title": lv.task_title.strip(),
        "mentor_message": lv.mentor_message.strip(),
        "hints": [h.strip() for h in lv.hints[:2]] if mode == "do" else [],
        "max_xp": PREDICT_POINTS * len(pauses) if mode == "watch" else DO_MAX_XP,
        "content": {
            "mode": mode,
            "situation": lv.situation.strip(),
            "artifact_lines": [x.rstrip() for x in lv.artifact_lines],
            "steps": steps,
            "pauses": pauses,
            "pool": pool,
        },
        "state": {"pause": 0, "predictions": [], "cards": [], "hinted_pauses": [], "submitted": False, "match": None, "comparison": None},
    }


# ---------------------------------------------------------------------------
# Hints: in shadow mode a hint belongs to the current pause point
# ---------------------------------------------------------------------------

def next_hint(level: dict) -> str | None:
    c, s = level["content"], level["state"]
    if c["mode"] != "watch":
        if s["submitted"]:
            raise EngineError(409, "سلّمت خطواتك بالفعل.")
        return None
    if s["pause"] >= len(c["pauses"]):
        raise EngineError(409, "لا توجد نقطة توقف حالية.")
    if s["pause"] in s["hinted_pauses"]:
        raise EngineError(409, "استخدمت تلميح هذه النقطة.")
    s["hinted_pauses"].append(s["pause"])
    return c["pauses"][s["pause"]]["hint"]


def can_hint(level: dict) -> bool:
    c, s = level["content"], level["state"]
    if c["mode"] == "watch":
        return s["pause"] < len(c["pauses"]) and s["pause"] not in s["hinted_pauses"]
    return not s["submitted"] and level["hints_shown"] < len(level["hints"])


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _compare(steps: list[dict], pool: list[dict], order: list[int]) -> tuple[int, dict]:
    chosen = [pool[i] for i in order]
    chosen_expert = [p["expert_index"] for p in chosen if p["expert_index"] is not None]
    n_expert = len(steps)
    recall = len(chosen_expert) / n_expert
    precision = len(chosen_expert) / len(chosen) if chosen else 0
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0
    pairs = [(a, b) for i, a in enumerate(chosen_expert) for b in chosen_expert[i + 1:]]
    in_order = sum(1 for a, b in pairs if a < b) / len(pairs) if pairs else 1.0
    match = round(100 * f1 * (0.5 + 0.5 * in_order))

    sorted_correct = sorted(chosen_expert)
    trainee = []
    for p in chosen:
        if p["expert_index"] is None:
            status = "extra"
        else:
            status = "match" if sorted_correct.index(p["expert_index"]) == chosen_expert.index(p["expert_index"]) else "out_of_order"
        trainee.append({"text": p["text"], "status": status})
    expert = [{"step": s["step"], "why": s["why"], "missed": i not in chosen_expert} for i, s in enumerate(steps)]
    return match, {"trainee": trainee, "expert": expert}


def act(db, activity, level: dict, action: str, payload: dict) -> dict:
    c, s = level["content"], level["state"]
    if action == "predict" and c["mode"] == "watch":
        if s["pause"] >= len(c["pauses"]):
            raise EngineError(409, "انتهت نقاط التوقف في هذه المرحلة.")
        pause = c["pauses"][s["pause"]]
        choice = payload.get("choice")
        if not isinstance(choice, int) or not 0 <= choice < len(pause["options"]):
            raise EngineError(422, "اختر بطاقة.")
        correct = choice == pause["correct"]
        step = c["steps"][pause["step_index"]]
        s["predictions"].append({"choice": choice, "correct": correct})
        if correct:
            s["cards"].append(step["golden"])
        s["pause"] += 1
        return {
            "result": "correct" if correct else "wrong",
            "xp_change": PREDICT_POINTS if correct else 0,
            "expert_step": step["step"],
            "why": step["why"],
            "card": step["golden"] if correct else None,
            "events": [{"type": "attempt", "correct": correct, "category": step["step"],
                        "details": {"pause": s["pause"], "explanation_ok": correct}}],
        }

    if action == "submit_steps" and c["mode"] == "do":
        if s["submitted"]:
            raise EngineError(409, "سلّمت خطواتك بالفعل.")
        order = payload.get("order")
        if not isinstance(order, list) or len(order) < 2 or len(set(order)) != len(order) or any(
            not isinstance(i, int) or not 0 <= i < len(c["pool"]) for i in order
        ):
            raise EngineError(422, "اختر خطواتك ورتّبها (خطوتان على الأقل).")
        match, comparison = _compare(c["steps"], c["pool"], order)
        s.update({"submitted": True, "order": order, "match": match, "comparison": comparison})
        missed = [e["step"] for e in comparison["expert"] if e["missed"]]
        return {
            "result": "compared",
            "xp_change": round(DO_MAX_XP * match / 100),
            "match": match,
            "events": [{"type": "attempt", "correct": match >= 70, "category": missed[0] if missed else None,
                        "details": {"match": match, "missed_steps": missed,
                                    "extra_steps": [t["text"] for t in comparison["trainee"] if t["status"] == "extra"]}}],
        }
    raise EngineError(422, "إجراء غير معروف.")


def reveal(level: dict) -> None:
    c, s = level["content"], level["state"]
    if c["mode"] == "watch":
        s["pause"] = len(c["pauses"])
    elif not s["submitted"]:
        s["submitted"] = True
        s["match"] = 0
        s["comparison"] = {"trainee": [], "expert": [{"step": x["step"], "why": x["why"], "missed": True} for x in c["steps"]]}


def public(level: dict) -> dict:
    c, s = level["content"], level["state"]
    view = {"kind": "shadow", "mode": c["mode"], "title": level["title"], "situation": c["situation"], "artifact_lines": c["artifact_lines"]}
    if c["mode"] == "watch":
        done = s["pause"] >= len(c["pauses"])
        visible_until = len(c["steps"]) if done else c["pauses"][s["pause"]]["step_index"]
        view.update({
            "visible_steps": [{"step": x["step"], "why": x["why"]} for x in c["steps"][:visible_until]],
            "current_pause": None if done else {"number": s["pause"] + 1, "of": len(c["pauses"]), "options": c["pauses"][s["pause"]]["options"]},
            "predictions": s["predictions"],
            "cards": s["cards"],
            "done": done,
        })
    else:
        view.update({
            "pool": [p["text"] for p in c["pool"]],
            "submitted": s["submitted"],
            "match": s["match"],
            "comparison": s["comparison"],
        })
    return view


def notes(level: dict) -> dict:
    c, s = level["content"], level["state"]
    if c["mode"] == "watch":
        missed = [c["steps"][c["pauses"][i]["step_index"]]["step"] for i, p in enumerate(s["predictions"]) if not p["correct"]]
        return {"mode": "watch (shadow)", "correct_predictions": sum(p["correct"] for p in s["predictions"]),
                "pauses": len(c["pauses"]), "mispredicted_steps": missed}
    comp = s["comparison"] or {"trainee": [], "expert": []}
    return {"mode": "do (reverse shadow)", "match_percent": s["match"],
            "missed_steps": [e["step"] for e in comp["expert"] if e["missed"]],
            "extra_steps": [t["text"] for t in comp["trainee"] if t["status"] == "extra"]}


def extra_badges(activity, level: dict) -> list[str]:
    c, s = level["content"], level["state"]
    if c["mode"] == "watch" and s["predictions"] and all(p["correct"] for p in s["predictions"]) and len(s["predictions"]) == len(c["pauses"]):
        return ["golden_collector"]
    if c["mode"] == "do" and (s["match"] or 0) >= 90:
        return ["expert_shadow"]
    return []


def rank_names(activity) -> tuple[str, str, str]:
    return "ظل مبتدئ", "ظل محترف", "ظل الخبير"
