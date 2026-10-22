"""🔐 غرفة الهروب المهنية (Escape room).

Three doors and a final (boss) door. Each door is a work problem: a decision
(single or multiple choice) whose consequence shapes the next door, then a
justification. Every opened door gives one digit of the exit code.

Points per door: decision 20 on the first try (−5 per retry, at least 5),
justification +10. A wrong decision shows its consequence and the mentor's
clue sheet; after 3 tries (2 in the final door) the answer is revealed and the
game moves on — nothing ends the game.
"""

import random

from .activity_schemas import EscapeFirstOutput, EscapeNextOutput
from .assessment_engine import EngineError

TOTAL_LEVELS = 4
PROMPT = "escape_door.txt"
FIRST_OUTPUT = EscapeFirstOutput
NEXT_OUTPUT = EscapeNextOutput
MISSION_FIELDS = (
    "`title` (short and catchy), `story` (2–3 short sentences, e.g. \"9 a.m. A report must reach the client, but the "
    "system is locked and full of problems. You have 4 doors, each opened by a code.\"), `goal` (one sentence), and `win_condition` (one sentence)."
)
RULES = {"answer": 20, "justify": 10}
ANSWER_POINTS, RETRY_COST, MIN_ANSWER_POINTS, JUSTIFY_POINTS = 20, 5, 5, 10
MAX_TRIES, MAX_BOSS_TRIES = 3, 2
MAX_LINES, MAX_LINE_CHARS, MAX_SCENARIO, MAX_OPTION = 12, 220, 700, 180


def validate(door, number: int, is_boss: bool) -> list[str]:
    p = []
    if not door.scenario.strip() or len(door.scenario) > MAX_SCENARIO:
        p.append(f"scenario is required and must be under {MAX_SCENARIO} characters.")
    if door.artifact_kind != "none" and not 2 <= len(door.artifact_lines) <= MAX_LINES:
        p.append(f"artifact_lines must have 2-{MAX_LINES} lines when artifact_kind is not none.")
    if any(len(line) > MAX_LINE_CHARS for line in door.artifact_lines):
        p.append(f"artifact lines must be under {MAX_LINE_CHARS} characters.")
    opts = [o.strip() for o in door.options]
    if not 4 <= len(opts) <= 5 or len(set(opts)) != len(opts) or not all(opts) or any(len(o) > MAX_OPTION for o in opts):
        p.append(f"options must be 4-5 distinct non-empty options under {MAX_OPTION} characters.")
    correct = set(door.correct_options)
    if not correct or any(not 0 <= i < len(opts) for i in correct) or len(correct) != len(door.correct_options):
        p.append("correct_options must be valid distinct indices.")
    if door.challenge_type == "choice" and len(correct) != 1:
        p.append("a choice door needs exactly 1 correct option.")
    if door.challenge_type == "multi_select" and not 2 <= len(correct) <= 3:
        p.append("a multi_select door needs 2-3 correct options.")
    if len(door.option_consequences) != len(opts) or not all(c.strip() for c in door.option_consequences):
        p.append("option_consequences must have one non-empty consequence per option.")
    just = [o.strip() for o in door.justification_options]
    if len(just) != 3 or len(set(just)) != 3 or not all(just) or not 0 <= door.correct_justification < 3:
        p.append("justification needs 3 distinct options and a valid correct_justification.")
    if not door.question.strip() or not door.justification_question.strip() or not door.clue_sheet.strip():
        p.append("question, justification_question and clue_sheet are required.")
    if not is_boss and (len(door.hints) != 2 or not all(h.strip() for h in door.hints)):
        p.append("exactly 2 hints are required.")
    return p


def build_level(door, number: int, is_boss: bool) -> dict:
    order = list(range(len(door.options)))
    random.shuffle(order)
    just_order = list(range(3))
    random.shuffle(just_order)
    return {
        "title": door.door_title.strip(),
        "mentor_message": door.mentor_message.strip(),
        "hints": [h.strip() for h in door.hints[:2]],
        "max_xp": ANSWER_POINTS + JUSTIFY_POINTS,
        "content": {
            "scenario": door.scenario.strip(),
            "artifact_kind": door.artifact_kind,
            "artifact_lines": [line.rstrip() for line in door.artifact_lines] if door.artifact_kind != "none" else [],
            "challenge_type": door.challenge_type,
            "question": door.question.strip(),
            "options": [door.options[i].strip() for i in order],
            "consequences": [door.option_consequences[i].strip() for i in order],
            "correct": sorted(order.index(i) for i in door.correct_options),
            "justification_question": door.justification_question.strip(),
            "justification_options": [door.justification_options[i].strip() for i in just_order],
            "correct_justification": just_order.index(door.correct_justification),
            "clue_sheet": door.clue_sheet.strip(),
        },
        "state": {
            "attempts": 0,
            "solved": False,
            "revealed": False,
            "chosen": None,
            "consequence": None,
            "clue_shown": False,
            "justified": False,
            "justification_ok": None,
            "digit": random.randint(0, 9),
        },
    }


def act(db, activity, level: dict, action: str, payload: dict) -> dict:
    c, s = level["content"], level["state"]
    if action == "answer":
        if s["solved"] or s["revealed"]:
            raise EngineError(409, "سبق أن أجبت عن هذا الباب.")
        selected = payload.get("selected")
        if not isinstance(selected, list) or not selected or any(
            not isinstance(i, int) or not 0 <= i < len(c["options"]) for i in selected
        ) or len(set(selected)) != len(selected):
            raise EngineError(422, "اختر إجابة صالحة.")
        if c["challenge_type"] == "choice" and len(selected) != 1:
            raise EngineError(422, "اختر خيارًا واحدًا.")
        s["attempts"] += 1
        s["chosen"] = sorted(selected)
        s["consequence"] = " ".join(c["consequences"][i] for i in sorted(selected))
        correct = sorted(selected) == c["correct"]
        tries = MAX_BOSS_TRIES if level["is_boss"] else MAX_TRIES
        gained = 0
        if correct:
            s["solved"] = True
            gained = max(MIN_ANSWER_POINTS, ANSWER_POINTS - RETRY_COST * (s["attempts"] - 1))
        elif s["attempts"] >= tries:
            s["revealed"] = True
        elif not level["is_boss"]:
            s["clue_shown"] = True
        return {
            "result": "solved" if correct else "revealed" if s["revealed"] else "retry",
            "xp_change": gained,
            "consequence": s["consequence"],
            "events": [{"type": "attempt", "correct": correct, "category": level["title"],
                        "details": {"attempt": s["attempts"], "selected": selected}}],
        }

    if action == "justify":
        if not (s["solved"] or s["revealed"]):
            raise EngineError(409, "اتخذ القرار أولًا.")
        if s["justified"]:
            raise EngineError(409, "سبق أن برّرت قرارك.")
        choice = payload.get("choice")
        if not isinstance(choice, int) or not 0 <= choice < len(c["justification_options"]):
            raise EngineError(422, "اختر تبريرًا صالحًا.")
        s["justified"] = True
        s["justification_ok"] = choice == c["correct_justification"]
        return {
            "result": "door_open",
            "xp_change": JUSTIFY_POINTS if s["justification_ok"] else 0,
            "justification_ok": s["justification_ok"],
            "digit": s["digit"],
            "events": [{"type": "justify", "correct": s["justification_ok"], "category": level["title"],
                        "details": {"explanation_ok": s["justification_ok"]}}],
        }
    raise EngineError(422, "إجراء غير معروف.")


def reveal(level: dict) -> None:
    s = level["state"]
    if not s["solved"]:
        s["revealed"] = True


def public(level: dict) -> dict:
    c, s = level["content"], level["state"]
    done = s["solved"] or s["revealed"]
    view = {
        "kind": "door",
        "title": level["title"],
        "scenario": c["scenario"],
        "artifact_kind": c["artifact_kind"],
        "artifact_lines": c["artifact_lines"],
        "challenge_type": c["challenge_type"],
        "question": c["question"],
        "options": c["options"],
        "state": {k: s[k] for k in ("attempts", "solved", "revealed", "chosen", "consequence", "clue_shown", "justified", "justification_ok")},
        "tries_left": (MAX_BOSS_TRIES if level["is_boss"] else MAX_TRIES) - s["attempts"],
    }
    if s["clue_shown"] or done:
        view["clue_sheet"] = c["clue_sheet"]
    if done:
        view.update({
            "correct": c["correct"],
            "justification_question": c["justification_question"],
            "justification_options": c["justification_options"],
        })
    if s["justified"] or level["finished"]:
        view["correct_justification"] = c["correct_justification"]
        view["digit"] = s["digit"]
    return view


def notes(level: dict) -> dict:
    c, s = level["content"], level["state"]
    return {
        "decision_taken": [c["options"][i] for i in (s["chosen"] or [])],
        "consequence_of_decision": s["consequence"],
        "solved": s["solved"],
        "attempts": s["attempts"],
        "justification_ok": s["justification_ok"],
    }


def extra_badges(activity, level: dict) -> list[str]:
    if not level["is_boss"]:
        return []
    doors = activity.levels[:-1] + [level]
    if all(d["state"]["solved"] and d["state"]["attempts"] == 1 and d["state"]["justification_ok"] for d in doors):
        return ["escape_artist"]
    return []
