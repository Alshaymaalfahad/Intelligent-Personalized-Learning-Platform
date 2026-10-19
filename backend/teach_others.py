"""🎓 علّم غيرك (Teach others).

«سعود» is a new trainee (an AI persona) with deliberate misconceptions. In each of
three rounds the trainee explains a concept in writing; Saud answers like a real
learner («طيب ليش؟», «أعطني مثال») and his understanding meter rises only with
clear, correct explanations. The boss: Saud takes a short test using only what he
was taught — if Saud passes, the trainee passes.
"""

import json
import random

from .activity_schemas import SaudQuizOutput, TeachFirstOutput, TeachNextOutput, TeachTurn
from .assessment_engine import EngineError
from .config import AI_FAST_EFFORT
from .question_generator import generate_validated, render_prompt

TOTAL_LEVELS = 4
PROMPT = "teach_level.txt"
FIRST_OUTPUT = TeachFirstOutput
NEXT_OUTPUT = TeachNextOutput
MISSION_FIELDS = (
    "`title`, `story` (2–3 short Arabic sentences, e.g. «هذا سعود، متدرب جديد بدأ اليوم، ومدير الفريق طلب منك تعلّمه…»), "
    "`goal`, and `win_condition` (e.g. «ينجح سعود في اختباره»)."
)
RULES = {"meter": 30, "quiz": 30}
ROUND_MAX_XP = 30
BOSS_MAX_XP = 30
MAX_TURNS = 4
MAX_METER_STEP = 40
SAUD_PASS = 2  # correct answers out of 3
MIN_TEXT, MAX_TEXT = 15, 1500


def _untrusted(text: str) -> str:
    return text.replace("<", "‹").replace(">", "›")


def validate(lv, number: int, is_boss: bool) -> list[str]:
    p = []
    for name in ("concept", "saud_opening"):
        if not getattr(lv, name).strip():
            p.append(f"{name} is required.")
    if not is_boss and not lv.misconception.strip():
        p.append("misconception is required.")
    if not 3 <= len(lv.key_points) <= 4 or not all(k.strip() for k in lv.key_points):
        p.append("key_points must have 3-4 points.")
    if not is_boss and (len(lv.hints) != 2 or not all(h.strip() for h in lv.hints)):
        p.append("exactly 2 hints are required.")
    if is_boss:
        if len(lv.quiz) != 3:
            p.append("the boss level needs exactly 3 quiz questions.")
        for q in lv.quiz:
            opts = [o.strip() for o in q.options]
            if len(opts) != 4 or len(set(opts)) != 4 or not all(opts) or not 0 <= q.correct < 4 or not q.question.strip():
                p.append("each quiz question needs text, 4 distinct options and a valid correct index.")
                break
    elif lv.quiz:
        p.append("quiz must be an empty list except in the boss level.")
    return p


def build_level(lv, number: int, is_boss: bool) -> dict:
    quiz = []
    for q in lv.quiz:
        order = list(range(4))
        random.shuffle(order)
        quiz.append({"question": q.question.strip(), "options": [q.options[i].strip() for i in order], "correct": order.index(q.correct)})
    return {
        "title": lv.concept.strip(),
        "mentor_message": lv.mentor_message.strip(),
        "hints": [h.strip() for h in lv.hints[:2]],
        "max_xp": BOSS_MAX_XP if is_boss else ROUND_MAX_XP,
        "content": {
            "concept": lv.concept.strip(),
            "misconception": lv.misconception.strip(),
            "key_points": [k.strip() for k in lv.key_points],
            "quiz": quiz,
        },
        "state": {
            "messages": [{"from": "saud", "text": lv.saud_opening.strip()}],
            "meter": 0,
            "covered": [],
            "turns": 0,
            "quiz_result": None,
            "saud_passed": None,
        },
    }


def _teaching_so_far(activity, level: dict) -> list[str]:
    texts = []
    for lv in activity.levels[:-1] + [level]:
        texts += [m["text"] for m in lv["state"]["messages"] if m["from"] == "trainee"]
    return texts


def _turn(activity, level: dict, text: str) -> TeachTurn:
    c, s = level["content"], level["state"]
    conversation = [
        {"from": m["from"], "text": _untrusted(m["text"]) if m["from"] == "trainee" else m["text"]}
        for m in s["messages"]
    ] + [{"from": "trainee", "text": _untrusted(text)}]
    prompt = render_prompt(
        "teach_turn.txt",
        specialization=activity.assessment.trainee.specialization,
        concept=c["concept"],
        misconception=c["misconception"],
        key_points=json.dumps(list(enumerate(c["key_points"])), ensure_ascii=False),
        meter=s["meter"],
        turns_left=MAX_TURNS - s["turns"] - 1,
        conversation=json.dumps(conversation, ensure_ascii=False, indent=2),
    )
    n = len(c["key_points"])

    def check(out: TeachTurn) -> list[str]:
        p = []
        if any(not 0 <= i < n for i in out.covered_points):
            p.append(f"covered_points must be indices 0-{n - 1}.")
        if not out.saud_reply.strip():
            p.append("saud_reply is required.")
        return p

    return generate_validated(prompt, TeachTurn, check, task="teach_turn", effort=AI_FAST_EFFORT)


def _quiz(activity, level: dict, text: str) -> SaudQuizOutput:
    c = level["content"]
    taught = [_untrusted(t) for t in _teaching_so_far(activity, level)] + [_untrusted(text)]
    misconceptions = [lv["content"]["misconception"] for lv in activity.levels[:-1]]
    prompt = render_prompt(
        "teach_quiz.txt",
        specialization=activity.assessment.trainee.specialization,
        misconceptions=json.dumps(misconceptions, ensure_ascii=False),
        teaching=json.dumps(taught, ensure_ascii=False, indent=2),
        quiz=json.dumps([{"index": i, "question": q["question"], "options": q["options"]} for i, q in enumerate(c["quiz"])], ensure_ascii=False, indent=2),
    )

    def check(out: SaudQuizOutput) -> list[str]:
        got = sorted(a.question_index for a in out.answers)
        if got != list(range(len(c["quiz"]))):
            return [f"answer every question exactly once (indices 0-{len(c['quiz']) - 1})."]
        if any(not 0 <= a.chosen_option < 4 for a in out.answers):
            return ["chosen_option must be 0-3."]
        return []

    return generate_validated(prompt, SaudQuizOutput, check, task="teach_quiz", effort=AI_FAST_EFFORT)


def act(db, activity, level: dict, action: str, payload: dict) -> dict:
    c, s = level["content"], level["state"]
    text = payload.get("text")
    if not isinstance(text, str) or not MIN_TEXT <= len(text.strip()) <= MAX_TEXT:
        raise EngineError(422, f"اكتب شرحك ({MIN_TEXT}–{MAX_TEXT} حرفًا).")
    text = text.strip()

    if action == "explain" and not level["is_boss"]:
        if s["turns"] >= MAX_TURNS or s["meter"] >= 100:
            raise EngineError(409, "انتهت محادثة هذه الجولة؛ أنهِ المرحلة.")
        out = _turn(activity, level, text)
        covered = sorted(set(s["covered"]) | set(out.covered_points))
        coverage_cap = round(100 * len(covered) / len(c["key_points"]))
        before = s["meter"]
        meter = before
        if out.accurate:
            meter = max(before, min(out.understanding, before + MAX_METER_STEP, coverage_cap, 100))
        s.update({"covered": covered, "meter": meter, "turns": s["turns"] + 1})
        s["messages"] += [{"from": "trainee", "text": text}, {"from": "saud", "text": out.saud_reply.strip()}]
        gained = round(ROUND_MAX_XP * meter / 100) - round(ROUND_MAX_XP * before / 100)
        return {
            "result": "replied",
            "xp_change": gained,
            "meter": meter,
            "meter_change": meter - before,
            "accurate": out.accurate,
            "clarity": out.clarity,
            "events": [{"type": "attempt", "correct": meter - before >= 10, "category": c["concept"],
                        "details": {"explanation_ok": out.accurate, "clarity": out.clarity, "has_example": out.has_example, "meter": meter}}],
        }

    if action == "final_lesson" and level["is_boss"]:
        if s["quiz_result"] is not None:
            raise EngineError(409, "دخل سعود الاختبار بالفعل.")
        out = _quiz(activity, level, text)
        s["messages"].append({"from": "trainee", "text": text})
        result = []
        for a in sorted(out.answers, key=lambda a: a.question_index):
            q = c["quiz"][a.question_index]
            result.append({**q, "saud_choice": a.chosen_option, "saud_correct": a.chosen_option == q["correct"], "reasoning": a.reasoning.strip()})
        correct = sum(r["saud_correct"] for r in result)
        s["quiz_result"] = result
        s["saud_passed"] = correct >= SAUD_PASS
        s["messages"].append({"from": "saud", "text": out.saud_message.strip()})
        return {
            "result": "quiz",
            "xp_change": round(BOSS_MAX_XP * correct / len(result)),
            "saud_passed": s["saud_passed"],
            "correct": correct,
            "events": [{"type": "attempt", "correct": s["saud_passed"], "category": c["concept"],
                        "details": {"saud_correct": correct, "explanation_ok": s["saud_passed"]}}],
        }
    raise EngineError(422, "إجراء غير معروف.")


def reveal(level: dict) -> None:
    pass


def public(level: dict) -> dict:
    c, s = level["content"], level["state"]
    view = {
        "kind": "teach",
        "title": level["title"],
        "concept": c["concept"],
        "messages": s["messages"],
        "meter": s["meter"],
        "turns_left": 0 if level["is_boss"] else MAX_TURNS - s["turns"],
        "quiz_size": len(c["quiz"]),
        "quiz_result": s["quiz_result"],
        "saud_passed": s["saud_passed"],
    }
    if level["finished"]:
        view["key_points"] = c["key_points"]
    return view


def notes(level: dict) -> dict:
    c, s = level["content"], level["state"]
    return {
        "concept": c["concept"],
        "misconception": c["misconception"],
        "meter": s["meter"],
        "covered_points": [c["key_points"][i] for i in s["covered"]],
        "missed_points": [k for i, k in enumerate(c["key_points"]) if i not in s["covered"]],
    }


def extra_badges(activity, level: dict) -> list[str]:
    result = level["state"]["quiz_result"]
    return ["inspiring_teacher"] if result and all(r["saud_correct"] for r in result) else []


def rank_names(activity) -> tuple[str, str, str]:
    return "معلّم مبتدئ", "معلّم متمكن", "معلّم ملهم"
