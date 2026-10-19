"""Behavior tracking: record every attempt inside a learning activity and turn the
log into a few meaningful signals.

Signals follow the operational concept (06 / BEHAVIOR SIGNALS). No single signal is
treated as proof of a gap: each one carries an interpretation and the decision it
suggests, and the reassessment uses them to choose what to verify.
"""

from datetime import datetime, timezone
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import LearningActivity, LearningEvent, utcnow

HIGH_HINTS_PER_LEVEL = 2
WEAK_JUSTIFICATION = 0.5
GOOD_DETECTION = 0.6
MANY_FALSE_ALARMS = 0.34  # share of clicks that hit a correct line
SLOW_SECONDS = 120
IMPROVEMENT = 0.2
MAX_POINTS_PER_ERROR = 30  # Gap Hunter: found 10 + category 5 + explanation 5 + fix 10


def _parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def record_event(
    db: Session,
    activity: LearningActivity,
    level: dict,
    event_type: str,
    *,
    correct: bool | None = None,
    category: str | None = None,
    details: dict | None = None,
    decision: str | None = None,
) -> None:
    """Append one attempt to the log (committed together with the game state)."""
    previous = db.scalars(
        select(LearningEvent)
        .where(LearningEvent.activity_pk == activity.id, LearningEvent.level == level["number"])
        .order_by(LearningEvent.id.desc())
        .limit(1)
    ).first()
    attempt = db.scalar(
        select(func.count()).select_from(LearningEvent)
        .where(LearningEvent.activity_pk == activity.id, LearningEvent.level == level["number"])
    ) + 1
    since = _aware(previous.created_at) if previous else _parse(level.get("started_at"))
    now = utcnow()
    db.add(LearningEvent(
        activity_pk=activity.id,
        competency_id=activity.competency_id,
        level=level["number"],
        event_type=event_type,
        correct=correct,
        error_category=category,
        attempt=attempt,
        hints_so_far=level["hints_used"],
        seconds_since_previous=round((now - since).total_seconds(), 1) if since else None,
        details=details,
        system_decision=decision,
        created_at=now,
    ))
    db.flush()  # the session does not autoflush; later reads in this request must see it


def _signal(sid: str, icon: str, title: str, value: str, interpretation: str, decision: str) -> dict:
    return {"id": sid, "icon": icon, "title": title, "value": value, "interpretation": interpretation, "decision": decision}


ATTEMPT_EVENTS = {"attempt", "mark_found", "false_alarm"}


def _level_max(level: dict) -> float:
    return level.get("max_xp") or len(level.get("errors", [])) * MAX_POINTS_PER_ERROR


def summarize(activities: list[LearningActivity], events: list[LearningEvent]) -> dict:
    """Metrics plus the signals worth acting on, for one or more completed activities on one gap.
    Works for every activity: each logs attempts (correct or not, with an error category),
    hints, justifications (details.explanation_ok) and lesson reviews."""
    attempts = [e for e in events if e.event_type in ATTEMPT_EVENTS]
    wrong = [e for e in attempts if e.correct is False]
    hints = [e for e in events if e.event_type == "hint"]
    reviews = [e for e in events if e.event_type == "review_lesson"]
    reasoned = [e for e in events if e.details and e.details.get("explanation_ok") is not None]

    levels = [lv for a in activities for lv in a.levels if lv.get("finished")]
    practice = [lv for lv in levels if not lv["is_boss"]]
    bosses = [lv for lv in levels if lv["is_boss"]]

    # Error types: what the trainee missed, chose wrongly, or justified wrongly — by category
    error_counts: dict[str, int] = {}
    for lv in levels:  # Gap Hunter: mistakes left unfound
        for err in lv.get("errors", []):
            if err["revealed"]:
                error_counts[err["category"]] = error_counts.get(err["category"], 0) + 1
    for e in wrong + [e for e in reasoned if not e.details["explanation_ok"]]:
        if e.error_category and e.event_type != "false_alarm":
            error_counts[e.error_category] = error_counts.get(e.error_category, 0) + 1
    repeated = {c: n for c, n in error_counts.items() if n >= 2}

    hunter_total = sum(len(lv.get("errors", [])) for lv in levels)
    found = [e for e in events if e.event_type == "mark_found"]
    if hunter_total:
        action_rate = len(found) / hunter_total
    else:
        action_rate = (len(attempts) - len(wrong)) / len(attempts) if attempts else 0
    explanation_rate = sum(bool(e.details["explanation_ok"]) for e in reasoned) / len(reasoned) if reasoned else None
    fixes = [e for e in events if e.details and e.details.get("fix_ok") is not None]
    fix_rate = sum(bool(e.details["fix_ok"]) for e in fixes) / len(fixes) if fixes else None
    hints_per_level = [lv["hints_used"] for lv in practice]
    wrong_rate = len(wrong) / len(attempts) if attempts else 0
    times = [e.seconds_since_previous for e in attempts if e.correct and e.seconds_since_previous is not None]
    median_time = median(times) if times else None
    accuracy = [round(max(0, lv["xp"]) / _level_max(lv), 2) for lv in practice if _level_max(lv)]
    boss_accuracy = round(max(0, bosses[-1]["xp"]) / _level_max(bosses[-1]), 2) if bosses and _level_max(bosses[-1]) else None

    signals = []
    if repeated:
        top = max(repeated, key=repeated.get)
        signals.append(_signal(
            "repeated_error", "❌", "نوع الخطأ وتكراره", f"«{top}» تكرر {repeated[top]} مرات",
            "خطأ متكرر في المفهوم نفسه.", "مهمة بديلة أو توضيح موجّه لهذا المفهوم.",
        ))
    if hints_per_level and sum(hints_per_level) / len(hints_per_level) >= HIGH_HINTS_PER_LEVEL:
        signals.append(_signal(
            "hint_reliance", "💡", "التلميحات المستخدمة", f"{sum(hints_per_level)} تلميحات في {len(hints_per_level)} مراحل",
            "اعتماد كبير على التلميحات.", "تقليل الدعم تدريجيًا ثم اختبار الاستقلالية.",
        ))
    if wrong_rate >= MANY_FALSE_ALARMS and len(attempts) >= 3:
        signals.append(_signal(
            "many_attempts", "🔁", "عدد المحاولات", f"{len(wrong)} محاولات خاطئة من {len(attempts)}",
            "محاولات كثيرة قبل الوصول للإجابة.", "تحليل موضع التعثر، دون افتراض ضعف تلقائي.",
        ))
    if median_time is not None and median_time >= SLOW_SECONDS and (repeated or wrong_rate >= MANY_FALSE_ALARMS):
        signals.append(_signal(
            "unusual_time", "⏱️", "الوقت في المهمة", f"حوالي {round(median_time)} ثانية لكل إجابة صحيحة",
            "وقت غير معتاد مع إشارات تعثر أخرى.", "فحص وضوح المهمة أو صعوبتها.",
        ))
    if explanation_rate is not None and action_rate >= GOOD_DETECTION and explanation_rate < WEAK_JUSTIFICATION:
        signals.append(_signal(
            "weak_justification", "🧠", "التبرير وجودته", f"ينفّذ صحيحًا {round(action_rate * 100)}% ويبرر صحيحًا {round(explanation_rate * 100)}%",
            "إجابة صحيحة مع تبرير ضعيف.", "سؤال متابعة يختبر الفهم الحقيقي.",
        ))
    if len(accuracy) >= 2 and accuracy[-1] - accuracy[0] >= IMPROVEMENT:
        signals.append(_signal(
            "improving", "📈", "التغير بين المحاولات", f"من {round(accuracy[0] * 100)}% إلى {round(accuracy[-1] * 100)}%",
            "تحسن بعد التغذية الراجعة.", "رفع التحدي واختبار النقل إلى موقف جديد.",
        ))
    if reviews:
        signals.append(_signal(
            "lesson_reviews", "📖", "الرجوع للشرح", f"رجع للشرح {len(reviews)} مرة أثناء النشاط",
            "يبحث عن الفهم بدل التخمين.", "سلوك إيجابي؛ يبقى الشرح متاحًا دون خصم.",
        ))

    return {
        "metrics": {
            "activities": len(activities),
            "action_rate": round(action_rate, 2),
            "explanation_rate": round(explanation_rate, 2) if explanation_rate is not None else None,
            "fix_rate": round(fix_rate, 2) if fix_rate is not None else None,
            "hints_per_level": hints_per_level,
            "hints_total": len(hints),
            "wrong_attempt_rate": round(wrong_rate, 2),
            "median_seconds_per_correct": round(median_time) if median_time is not None else None,
            "level_accuracy": accuracy,
            "boss_accuracy": boss_accuracy,
            "lesson_reviews": len(reviews),
            "error_types": error_counts,
        },
        "signals": signals,
    }


def competency_behavior(db: Session, assessment, competency_id: str) -> dict:
    activities = [a for a in assessment.activities if a.competency_id == competency_id and a.status == "completed"]
    if not activities:
        return {"metrics": {}, "signals": []}
    events = list(db.scalars(
        select(LearningEvent).where(LearningEvent.activity_pk.in_([a.id for a in activities])).order_by(LearningEvent.id)
    ))
    return summarize(activities, events)


def activity_behavior(db: Session, activity: LearningActivity) -> dict:
    events = list(db.scalars(select(LearningEvent).where(LearningEvent.activity_pk == activity.id).order_by(LearningEvent.id)))
    return summarize([activity], events)
