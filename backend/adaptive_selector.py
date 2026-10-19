"""Decides what the NEXT question must measure, from the answers so far.

The AI writes the question, but this module — not the AI — chooses its target:
which competency, how hard, which Bloom level and which question types are allowed.
That keeps coverage guaranteed (every skill / knowledge area gets enough evidence)
while each question still adapts to the previous answer.

Skills section (قياس المهارة): 5 skills (3 hard, 2 soft) × 2 questions, asked in pairs.
  - 1st question of a skill: difficulty from the trainee's running level.
  - 2nd question: harder if the 1st was right (confirm solid competence),
    easier and on the core of the skill if it was wrong (basic competence or gap?).
  - No written answers here: every question is quick to answer.

Knowledge section (قياس المعرفة): driven by Bloom's levels, 4–5 areas, 10 questions.
  - Each area starts low (remembering) if a related skill was weak, otherwise at understanding.
  - Correct → climb one Bloom level; wrong → go down one level.
  - Every question type appears at least once.

In both sections the engine picks ONE question type per question, preferring the type
used least so far, so formats are mixed rather than left to the model's habits.
"""

import random

from dataclasses import dataclass, field

QUESTIONS_PER_SECTION = 10
QUESTIONS_PER_SKILL = 2
MAX_KNOWLEDGE_OPEN_ENDED = 1
PASS_FRACTION = 0.5  # a question counts as "answered correctly" at ≥ 50% of its points

BLOOM_LEVELS = ["remembering", "understanding", "applying", "analyzing", "evaluating", "creating"]
BLOOM_AR = {
    "remembering": "التذكر",
    "understanding": "الفهم",
    "applying": "التطبيق",
    "analyzing": "التحليل",
    "evaluating": "التقييم",
    "creating": "الابتكار",
}

SKILL_TYPES = ["scenario", "true_false", "ordering", "error_detection", "multiple_choice"]
SKILL_BLOOM_BY_DIFFICULTY = {1: "applying", 2: "applying", 3: "analyzing", 4: "evaluating", 5: "evaluating"}

KNOWLEDGE_TYPES = ["true_false", "multiple_choice", "scenario", "ordering", "open_ended"]
KNOWLEDGE_TYPES_BY_LEVEL = {
    "remembering": ["true_false", "multiple_choice", "ordering"],
    "understanding": ["multiple_choice", "true_false", "scenario", "ordering"],
    "applying": ["scenario", "multiple_choice", "ordering"],
    "analyzing": ["scenario", "multiple_choice"],
    "evaluating": ["open_ended", "scenario"],
    "creating": ["open_ended"],
}
KNOWLEDGE_DIFFICULTY_BY_LEVEL = {
    "remembering": 1, "understanding": 2, "applying": 3, "analyzing": 4, "evaluating": 4, "creating": 5,
}
WEAK_SKILL_STATUSES = {"potential_gap", "likely_gap", "insufficient_evidence"}


@dataclass
class Target:
    competency_id: str
    difficulty: int
    bloom_level: str
    allowed_types: list[str]  # the engine narrows this to one type
    reason: str  # Arabic; shown in the question review and sent to the AI
    previous_on_competency: list = field(default_factory=list)


def passed(q) -> bool:
    return q.max_score > 0 and (q.earned_score or 0) / q.max_score >= PASS_FRACTION


def _clamp(value: int, lo: int = 1, hi: int = 5) -> int:
    return max(lo, min(hi, value))


def _open_budget_left(answered: list) -> bool:
    return sum(1 for q in answered if q.question_type == "open_ended") < MAX_KNOWLEDGE_OPEN_ENDED


def _least_used(candidates: list[str], answered: list) -> str:
    """Mix formats: pick the candidate type used least so far (random among ties)."""
    counts = {t: sum(1 for q in answered if q.question_type == t) for t in candidates}
    fewest = min(counts.values())
    return random.choice([t for t in candidates if counts[t] == fewest])


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

def _running_level(answered: list) -> int:
    """Difficulty for a new skill's first question, from all answers so far."""
    if not answered:
        return 3
    moves = [q.difficulty + (1 if passed(q) else -1) for q in answered]
    return _clamp(round(sum(moves) / len(moves)), 2, 4)


def next_skill_target(skills: list[dict], answered: list, start_difficulty: dict[str, int] | None = None) -> Target | None:
    """`start_difficulty` (reassessment) fixes the first question's difficulty per skill."""
    if len(answered) >= len(skills) * QUESTIONS_PER_SKILL:
        return None
    by_skill = {s["competency_id"]: [q for q in answered if q.competency_id == s["competency_id"]] for s in skills}

    # Finish the current pair first: the follow-up depends directly on the previous answer.
    last = answered[-1] if answered else None
    if last and len(by_skill.get(last.competency_id, [])) < QUESTIONS_PER_SKILL:
        if passed(last):
            difficulty = _clamp(last.difficulty + 1)
            reason = (
                f"أجاب المتدرب عن السؤال السابق في هذه المهارة إجابة صحيحة (صعوبة {last.difficulty}). "
                "السؤال التالي أصعب وعلى جانب مختلف من المهارة، للتأكد من أن الكفاءة راسخة وليست مصادفة."
            )
        else:
            difficulty = _clamp(last.difficulty - 1)
            reason = (
                f"أخطأ المتدرب في السؤال السابق في هذه المهارة (صعوبة {last.difficulty}). "
                "السؤال التالي أبسط ويركز على أساس المهارة، لنميّز بين نقص الأساس وخطأ عابر، "
                "ويكشف إن كان سوء الفهم الذي ظهر في الإجابة السابقة ما زال قائمًا."
            )
        qtype = _least_used([t for t in SKILL_TYPES if t != last.question_type], answered)
        return Target(
            competency_id=last.competency_id,
            difficulty=difficulty,
            bloom_level=SKILL_BLOOM_BY_DIFFICULTY[difficulty],
            allowed_types=[qtype],
            reason=reason,
            previous_on_competency=by_skill[last.competency_id],
        )

    # Otherwise open the next skill, most important first.
    remaining = [s for s in sorted(skills, key=lambda s: -s["importance"]) if not by_skill[s["competency_id"]]]
    if not remaining:
        return None
    skill = remaining[0]
    difficulty = (start_difficulty or {}).get(skill["competency_id"]) or _running_level(answered)
    reason = (
        "أول سؤال في هذه المهارة. الصعوبة مبنية على مستوى المتدرب في الأسئلة السابقة."
        if answered
        else "أول سؤال في التقييم: صعوبة متوسطة لتحديد نقطة البداية."
    )
    return Target(
        competency_id=skill["competency_id"],
        difficulty=difficulty,
        bloom_level=SKILL_BLOOM_BY_DIFFICULTY[difficulty],
        allowed_types=[_least_used(SKILL_TYPES, answered)],
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Knowledge (Bloom-driven)
# ---------------------------------------------------------------------------

def _start_level(area: dict, skill_results: list[dict]) -> str:
    status = {r["competency_id"]: r["status"] for r in skill_results}
    weak = any(status.get(sid) in WEAK_SKILL_STATUSES for sid in area.get("related_skill_ids", []))
    return "remembering" if weak else "understanding"


def _step(level: str, up: bool) -> str:
    i = BLOOM_LEVELS.index(level) + (1 if up else -1)
    return BLOOM_LEVELS[max(0, min(len(BLOOM_LEVELS) - 1, i))]


def _pick_area(areas: list[dict], by_area: dict[str, list], last) -> tuple[dict, str]:
    """Returns (area, why). Pairs first, then extra questions where evidence is most uncertain."""
    if last and len(by_area[last.competency_id]) == 1:
        area = next(a for a in areas if a["competency_id"] == last.competency_id)
        return area, "follow_up"
    fresh = [a for a in areas if not by_area[a["competency_id"]]]
    if fresh:
        return fresh[0], "new"

    def uncertainty(a):
        qs = by_area[a["competency_id"]]
        results = [passed(q) for q in qs]
        mixed = 0 if len(set(results)) > 1 else 1  # one right + one wrong = most uncertain
        return (len(qs), mixed, -a["importance"])

    return min(areas, key=uncertainty), "extra"


def next_knowledge_target(
    areas: list[dict],
    answered: list,
    skill_results: list[dict],
    total: int = QUESTIONS_PER_SECTION,
    start_level: dict[str, str] | None = None,
) -> Target | None:
    """`total` and `start_level` (Bloom level per area) are set for a reassessment."""
    if len(answered) >= total:
        return None
    by_area = {a["competency_id"]: [q for q in answered if q.competency_id == a["competency_id"]] for a in areas}
    last = answered[-1] if answered else None
    area, why = _pick_area(areas, by_area, last)
    previous = by_area[area["competency_id"]]

    if previous:
        prev = previous[-1]
        ok = passed(prev)
        level = _step(prev.bloom_level, up=ok)
        reason = (
            f"أجاب المتدرب صحيحًا عن سؤال في هذا المجال بمستوى «{BLOOM_AR[prev.bloom_level]}»، فننتقل إلى مستوى أعلى: «{BLOOM_AR[level]}»."
            if ok
            else f"أخطأ المتدرب في سؤال بمستوى «{BLOOM_AR[prev.bloom_level]}»، فننزل إلى مستوى «{BLOOM_AR[level]}» لنتحقق من الأساس."
        )
        if why == "extra":
            reason = "سؤال إضافي لأن الأدلة في هذا المجال غير حاسمة. " + reason
    elif start_level and area["competency_id"] in start_level:
        level = start_level[area["competency_id"]]
        reason = f"أول سؤال في هذا المجال، ويبدأ من مستوى «{BLOOM_AR[level]}» بناءً على ما تدرّب عليه المتدرب."
    else:
        level = _start_level(area, skill_results)
        reason = (
            "أول سؤال في هذا المجال، ويبدأ من مستوى «التذكر» لأن مهارة مرتبطة به ظهرت فيها فجوة."
            if level == "remembering"
            else "أول سؤال في هذا المجال، ويبدأ من مستوى «الفهم»."
        )

    allowed = list(KNOWLEDGE_TYPES_BY_LEVEL[level])
    if not _open_budget_left(answered):
        allowed = [t for t in allowed if t != "open_ended"]
        if not allowed:  # "creating" needs a written answer; fall back one level
            level = "evaluating"
            allowed = ["scenario"]

    # Guarantee the four question types all appear in the section.
    used = {q.question_type for q in answered}
    missing = [t for t in KNOWLEDGE_TYPES if t not in used and (t != "open_ended" or _open_budget_left(answered))]
    remaining_slots = total - len(answered)
    if total >= len(KNOWLEDGE_TYPES) and missing and len(missing) >= remaining_slots:
        compatible = [t for t in allowed if t in missing]
        if compatible:
            allowed = compatible
        else:
            forced = missing[0]
            level = min(
                (lv for lv, types in KNOWLEDGE_TYPES_BY_LEVEL.items() if forced in types),
                key=lambda lv: abs(BLOOM_LEVELS.index(lv) - BLOOM_LEVELS.index(level)),
            )
            allowed = [forced]

    return Target(
        competency_id=area["competency_id"],
        difficulty=KNOWLEDGE_DIFFICULTY_BY_LEVEL[level],
        bloom_level=level,
        allowed_types=[_least_used(allowed, answered)],
        reason=reason,
        previous_on_competency=previous,
    )
