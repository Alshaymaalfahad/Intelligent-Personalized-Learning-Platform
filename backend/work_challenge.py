"""🧩 تحديات من واقع العمل (Work challenge).

A message from a manager or client with acceptance criteria. The trainee writes
a real deliverable; an AI reviewer in the sender's persona checks every
criterion and gives stars. The trainee can revise and resubmit (the best
submission counts — resubmitting never lowers the score).

Levels: 1 the task, 2 a surprise update to the same task (changed requirements,
like real work), 3 the boss: a new task, no hints, fewer submissions.
"""

import json

from .activity_schemas import WorkFirstOutput, WorkNextOutput, WorkReview
from .assessment_engine import EngineError
from .config import AI_FAST_EFFORT
from .question_generator import generate_validated, render_prompt

TOTAL_LEVELS = 3
PROMPT = "work_task.txt"
FIRST_OUTPUT = WorkFirstOutput
NEXT_OUTPUT = WorkNextOutput
MISSION_FIELDS = (
    "`title`, `story` (2–3 short Arabic sentences), `goal`, `win_condition` (e.g. «سلّم مخرجًا يرضي العميل»), "
    "and `job_title` (the trainee's Arabic job title in this specialization, e.g. «محلل نظم» or «مطور برمجيات»)."
)
POINTS_PER_CRITERION_POINT = 10
STATUS_WEIGHT = {"met": 1.0, "partial": 0.5, "missing": 0.0}
MAX_SUBMISSIONS, MAX_BOSS_SUBMISSIONS = 3, 2
MIN_TEXT, MAX_TEXT = 20, 3000


def validate(task, number: int, is_boss: bool) -> list[str]:
    p = []
    for name in ("sender_name", "sender_role", "subject", "message", "deliverable_instructions", "model_answer"):
        if not getattr(task, name).strip():
            p.append(f"{name} is required.")
    if len(task.message) > 900:
        p.append("message must be under 900 characters (short and realistic).")
    if len(task.input_lines) > 14 or any(len(line) > 220 for line in task.input_lines):
        p.append("input_lines: at most 14 lines, each under 220 characters.")
    crit = task.acceptance_criteria
    if not 3 <= len(crit) <= 5 or any(not c.criterion.strip() or not 1 <= c.points <= 3 for c in crit):
        p.append("acceptance_criteria: 3-5 criteria, each with text and 1-3 points.")
    if not is_boss and (len(task.hints) != 2 or not all(h.strip() for h in task.hints)):
        p.append("exactly 2 hints are required.")
    return p


def build_level(task, number: int, is_boss: bool) -> dict:
    criteria = [{"criterion": c.criterion.strip(), "points": c.points} for c in task.acceptance_criteria]
    return {
        "title": task.subject.strip(),
        "mentor_message": task.mentor_message.strip(),
        "hints": [h.strip() for h in task.hints[:2]],
        "max_xp": sum(c["points"] for c in criteria) * POINTS_PER_CRITERION_POINT,
        "content": {
            "sender_name": task.sender_name.strip(),
            "sender_role": task.sender_role.strip(),
            "subject": task.subject.strip(),
            "message": task.message.strip(),
            "input_title": task.input_title.strip(),
            "input_lines": [line.rstrip() for line in task.input_lines],
            "deliverable_instructions": task.deliverable_instructions.strip(),
            "criteria": criteria,
            "model_answer": task.model_answer.strip(),
            "surprise": number == 2,
        },
        "state": {"submissions": [], "best_percent": 0},
    }


def _review(activity, level: dict, text: str) -> WorkReview:
    c = level["content"]
    criteria = c["criteria"]
    prompt = render_prompt(
        "work_review.txt",
        specialization=activity.assessment.trainee.specialization,
        sender=f"{c['sender_name']} — {c['sender_role']}",
        task=json.dumps({k: c[k] for k in ("subject", "message", "input_title", "input_lines", "deliverable_instructions")}, ensure_ascii=False, indent=2),
        criteria=json.dumps(criteria, ensure_ascii=False, indent=2),
        model_answer=c["model_answer"],
        deliverable=text.replace("<", "‹").replace(">", "›"),
    )

    def check(out: WorkReview) -> list[str]:
        return [] if len(out.criteria) == len(criteria) else [f"Return exactly {len(criteria)} criteria reviews, in order."]

    return generate_validated(prompt, WorkReview, check, task="work_review", effort=AI_FAST_EFFORT)


def act(db, activity, level: dict, action: str, payload: dict) -> dict:
    if action != "submit":
        raise EngineError(422, "إجراء غير معروف.")
    s, c = level["state"], level["content"]
    limit = MAX_BOSS_SUBMISSIONS if level["is_boss"] else MAX_SUBMISSIONS
    if len(s["submissions"]) >= limit:
        raise EngineError(409, "استخدمت كل محاولات التسليم في هذه المرحلة.")
    text = payload.get("text")
    if not isinstance(text, str) or not MIN_TEXT <= len(text.strip()) <= MAX_TEXT:
        raise EngineError(422, f"اكتب مخرجك ({MIN_TEXT}–{MAX_TEXT} حرفًا).")
    text = text.strip()

    review = _review(activity, level, text)
    results = []
    earned = 0.0
    for criterion, r in zip(c["criteria"], review.criteria):
        earned += criterion["points"] * STATUS_WEIGHT[r.status]
        results.append({"criterion": criterion["criterion"], "points": criterion["points"], "status": r.status, "comment": r.comment.strip()})
    total = sum(x["points"] for x in c["criteria"])
    percent = round(100 * earned / total) if total else 0
    stars = 1 + round(4 * percent / 100)
    submission = {
        "text": text, "percent": percent, "stars": stars, "criteria": results,
        "feedback": review.manager_feedback.strip(), "confidence": max(0.0, min(1.0, review.confidence)),
    }
    s["submissions"].append(submission)
    gained = round((max(percent, s["best_percent"]) - s["best_percent"]) / 100 * level["max_xp"])
    s["best_percent"] = max(percent, s["best_percent"])
    missing = [r["criterion"] for r in results if r["status"] != "met"]
    return {
        "result": "reviewed",
        "xp_change": gained,
        "submission": submission,
        "events": [{"type": "attempt", "correct": percent >= 70, "category": missing[0] if missing else None,
                    "details": {"percent": percent, "stars": stars, "submission": len(s["submissions"]),
                                "missing_criteria": missing}}],
    }


def reveal(level: dict) -> None:
    pass


def public(level: dict) -> dict:
    c, s = level["content"], level["state"]
    limit = MAX_BOSS_SUBMISSIONS if level["is_boss"] else MAX_SUBMISSIONS
    view = {
        "kind": "work",
        "title": level["title"],
        **{k: c[k] for k in ("sender_name", "sender_role", "subject", "message", "input_title", "input_lines",
                             "deliverable_instructions", "criteria", "surprise")},
        "submissions": s["submissions"],
        "best_percent": s["best_percent"],
        "best_stars": max((x["stars"] for x in s["submissions"]), default=0),
        "submissions_left": limit - len(s["submissions"]),
    }
    if level["finished"]:
        view["model_answer"] = c["model_answer"]
    return view


def notes(level: dict) -> dict:
    c, s = level["content"], level["state"]
    best = max(s["submissions"], key=lambda x: x["percent"], default=None)
    return {
        "task_subject": c["subject"],
        "task_message": c["message"],
        "criteria": [x["criterion"] for x in c["criteria"]],
        "best_percent": s["best_percent"],
        "submissions": len(s["submissions"]),
        "missed_criteria": [r["criterion"] for r in best["criteria"] if r["status"] != "met"] if best else [],
    }


def extra_badges(activity, level: dict) -> list[str]:
    return ["client_star"] if any(x["stars"] == 5 for x in level["state"]["submissions"]) else []


def rank_names(activity) -> tuple[str, str, str]:
    job = (activity.mission or {}).get("job_title") or "موظف"
    return "متدرب", job, f"{job} أول"
