"""The five gamified learning activities and which one fits which gap.

Every activity shares one game system (mission card, levels, XP, hint coins, AI mentor,
boss level, badges); the AI fills the template with content for the specific gap.
"""

ACTIVITIES = {
    "escape_room": {
        "name": "Escape Room",
        "icon": "🔐",
        "summary": "Locked doors, each a work problem. Every decision unlocks part of the code and shapes the next door.",
        "best_for": "Procedural skills that need a chain of decisions.",
        "available": True,
    },
    "gap_hunter": {
        "name": "Gap Hunter",
        "icon": "🕵️",
        "summary": "A work artifact with hidden mistakes. Catch them, classify them, justify them and fix them.",
        "best_for": "Diagnosis, error spotting and review skills.",
        "available": True,
    },
    "work_challenge": {
        "name": "Real-World Challenges",
        "icon": "🧩",
        "summary": "A task from a manager or client, with acceptance criteria, a surprise change, and a manager review.",
        "best_for": "Soft skills and applying a whole skill in a real task.",
        "available": True,
    },
    "shadow": {
        "name": "Shadow & Reverse Shadow",
        "icon": "👥",
        "summary": "Watch an expert solve it and predict the next step, then solve it yourself and compare with the expert.",
        "best_for": "Big gaps: learn the expert's method before working alone.",
        "available": True,
    },
    "teach_others": {
        "name": "Teach Someone",
        "icon": "🎓",
        "summary": "Saud is a new trainee with misconceptions. Explain until he passes his test.",
        "best_for": "Understanding gaps: what you don't understand well, you can't explain.",
        "available": True,
    },
}

DIAGNOSTIC_TYPES = {"error_detection", "true_false", "multiple_choice"}


def choose_activities(result: dict, missed_types: list[str]) -> list[str]:
    """Ordered activity ids for one gap: the first is the recommended one, the rest
    are alternatives offered when the gap persists ("جرّب طريقة ثانية")."""
    dimension, kind, status = result["dimension"], result.get("skill_kind"), result["status"]
    if dimension == "skill" and kind == "soft":
        order = ["work_challenge", "shadow", "teach_others", "escape_room", "gap_hunter"]
    elif dimension == "skill" and status == "likely_gap":
        order = ["shadow", "escape_room", "gap_hunter", "work_challenge", "teach_others"]
    elif dimension == "skill":
        diagnostic = sum(t in DIAGNOSTIC_TYPES for t in missed_types) >= len(missed_types) / 2 if missed_types else True
        order = (
            ["gap_hunter", "escape_room", "work_challenge", "shadow", "teach_others"]
            if diagnostic
            else ["escape_room", "gap_hunter", "work_challenge", "shadow", "teach_others"]
        )
    elif status == "likely_gap":
        order = ["shadow", "teach_others", "gap_hunter", "escape_room", "work_challenge"]
    else:
        order = ["teach_others", "gap_hunter", "shadow", "escape_room", "work_challenge"]
    return order


def activity_card(activity_id: str) -> dict:
    return {"activity_type": activity_id, **ACTIVITIES[activity_id]}
