"""API entry point. Run from the project root (binds to this machine only):

    uvicorn backend.main:app --reload
"""

import base64
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import assessment_engine as engine
from . import activity_core, gap_hunter, journey, lesson, reassessment
from .behavior import record_event
from . import config
from .ai_client import AIError
from .i18n import content_lang, localize, parse_header, request_lang
from .catalog import SPECIALIZATIONS
from .skills_catalog import localized as skills_localized
from .database import get_db, init_db
from .learning_engine import check_available
from .models import Assessment, LearningActivity, LearningEvent, Lesson, Question, Trainee
from .schemas import JourneyCreate, ActivityAction, ActivityCreate, AnswerSubmit, LessonAnswer, LessonCreate, AssessmentCreate, HuntJustify, HuntMark, QuestionReviewIn, TraineeCreate, TraineeOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if not config.ai_configured():
        logging.getLogger("startup").warning("AI API key is not set (AI_PROVIDER=%s) — run: python -m backend.set_api_key", config.AI_PROVIDER)
    yield


app = FastAPI(title="Intelligent Personalized Learning Platform", lifespan=lifespan)

SECURITY_HEADERS = {
    # Only our own scripts/styles may run; AI-generated text is always inserted as text, never HTML.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _has_access(request: Request) -> bool:
    """HTTP Basic auth: any username, password = ACCESS_CODE."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return False
    try:
        _, _, password = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    return secrets.compare_digest(password.encode(), config.ACCESS_CODE.encode())


@app.middleware("http")
async def access_code(request: Request, call_next):
    # /api/health stays open for the hosting platform's health check.
    if config.ACCESS_CODE and request.url.path != "/api/health" and not _has_access(request):
        return JSONResponse(
            status_code=401,
            content={"detail": localize("رمز الدخول مطلوب.")},
            headers={"WWW-Authenticate": 'Basic realm="Intelligent Learning Platform", charset="UTF-8"'},
        )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    else:
        # Always revalidate pages/scripts (cheap thanks to ETag), so a code update is
        # never mixed with an old cached script.
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.middleware("http")
async def language(request: Request, call_next):
    """Interface language of this request (X-Lang: en | ar); used to localize messages."""
    header = request.headers.get("x-lang")
    token = request_lang.set(parse_header(header))
    content_token = content_lang.set(parse_header(header) if header else None)
    try:
        return await call_next(request)
    finally:
        content_lang.reset(content_token)
        request_lang.reset(token)


@app.exception_handler(AIError)
async def ai_error_handler(_: Request, exc: AIError):
    code = status.HTTP_502_BAD_GATEWAY if exc.retryable else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content={"detail": localize(exc.user_message), "retryable": exc.retryable})


@app.exception_handler(engine.EngineError)
async def engine_error_handler(_: Request, exc: engine.EngineError):
    return JSONResponse(status_code=exc.status_code, content={"detail": localize(exc.message)})


@app.exception_handler(HTTPException)
async def localized_http_error(request: Request, exc: HTTPException):
    if isinstance(exc.detail, str):
        exc.detail = localize(exc.detail)
    return await http_exception_handler(request, exc)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def _get_trainee(db: Session, trainee_id: str) -> Trainee:
    trainee = db.scalar(select(Trainee).where(Trainee.trainee_id == trainee_id.strip().upper()))
    if trainee is None:
        raise HTTPException(status_code=404, detail="Trainee not found")
    return trainee


def _get_assessment(db: Session, assessment_id: str) -> Assessment:
    assessment = db.scalar(select(Assessment).where(Assessment.assessment_id == assessment_id.strip().upper()))
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


def _phase(phase: str) -> str:
    if phase not in engine.PHASES:
        raise HTTPException(status_code=404, detail="Unknown phase")
    return phase


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "ai_configured": config.ai_configured()}


# ---------------------------------------------------------------------------
# Skills map & journey (the trainee picks skills; no placement test)
# ---------------------------------------------------------------------------

@app.get("/api/skills")
def list_skills():
    return skills_localized(request_lang.get())


def _get_journey(db: Session, journey_id: str) -> Assessment:
    found = _get_assessment(db, journey_id)
    if found.kind != "journey":
        raise HTTPException(status_code=404, detail="Journey not found")
    return found


@app.post("/api/journeys", status_code=status.HTTP_201_CREATED)
def create_journey(payload: JourneyCreate, db: Session = Depends(get_db)):
    created = journey.create(db, payload.trainee_id, payload.new_trainee, payload.language, payload.selections)
    return journey.view(db, created, request_lang.get())


@app.get("/api/journeys/{journey_id}")
def get_journey(journey_id: str, db: Session = Depends(get_db)):
    return journey.view(db, _get_journey(db, journey_id), request_lang.get())


@app.get("/api/specializations")
def list_specializations():
    return SPECIALIZATIONS


@app.post("/api/trainees", response_model=TraineeOut, status_code=status.HTTP_201_CREATED)
def create_trainee(payload: TraineeCreate, db: Session = Depends(get_db)):
    trainee = Trainee(
        language=payload.language,
        specialization=payload.specialization,
        interests=payload.interests,
        additional_message=payload.additional_message,
        profile_status="completed",
    )
    db.add(trainee)
    db.flush()  # assigns the numeric id
    trainee.trainee_id = f"TR-{trainee.id:04d}"
    db.commit()
    return trainee


@app.get("/api/trainees/{trainee_id}", response_model=TraineeOut)
def get_trainee(trainee_id: str, db: Session = Depends(get_db)):
    return _get_trainee(db, trainee_id)


XP_PER_LEVEL = 500


def _streak(days: set) -> int:
    """Consecutive active days ending today (or yesterday, so the streak survives until tonight)."""
    from datetime import date, timedelta

    today = date.today()
    current = today if today in days else today - timedelta(days=1)
    streak = 0
    while current in days:
        streak += 1
        current -= timedelta(days=1)
    return streak


@app.get("/api/trainees/{trainee_id}/progress")
def trainee_progress(trainee_id: str, db: Session = Depends(get_db)):
    """Everything the app shell shows: XP, level, streak, badges, latest assessment — all from real activity."""
    trainee = _get_trainee(db, trainee_id)
    assessments = sorted(trainee.assessments, key=lambda a: a.id)
    activities = [act for a in assessments for act in a.activities]
    activity_ids = [act.id for act in activities]
    days = {a.created_at.date() for a in assessments} | {a.updated_at.date() for a in assessments if a.updated_at}
    if activity_ids:
        days |= {e.created_at.date() for e in db.scalars(select(LearningEvent).where(LearningEvent.activity_pk.in_(activity_ids)))}
    badges: dict[str, int] = {}
    for act in activities:
        for badge in act.badges:
            badges[badge] = badges.get(badge, 0) + 1
    xp = sum(act.xp for act in activities)
    passed = sum(
        1 for a in assessments for p in (a.learning_progress or {}).values() if p.get("status") == "passed"
    )
    initial = [a for a in assessments if (a.kind or "initial") == "initial"]
    assessments_only = [a for a in assessments if a.kind != "journey"]
    latest = assessments_only[-1] if assessments_only else None
    return {
        "trainee_id": trainee.trainee_id,
        "language": trainee.language,
        "xp": xp,
        "level": 1 + xp // XP_PER_LEVEL,
        "level_xp": xp % XP_PER_LEVEL,
        "xp_per_level": XP_PER_LEVEL,
        "streak_days": _streak(days),
        "badges": [{"id": k, "count": v} for k, v in badges.items()],
        "activities_completed": sum(1 for act in activities if act.status == "completed"),
        "gaps_passed": passed,
        "latest_assessment": {"assessment_id": latest.assessment_id, "status": latest.status, "kind": latest.kind or "initial"} if latest else None,
        "first_assessment_id": initial[0].assessment_id if initial else None,
        "journey_id": (j := journey.latest_for(trainee)) and j.assessment_id,
        "journey_complete": bool(j) and journey.is_complete(j),
    }


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------

@app.post("/api/assessments", status_code=status.HTTP_201_CREATED)
def create_assessment(payload: AssessmentCreate, db: Session = Depends(get_db)):
    trainee = _get_trainee(db, payload.trainee_id)  # no questions before a saved profile
    return engine.state_view(engine.create_assessment(db, trainee))


@app.get("/api/assessments/{assessment_id}")
def get_assessment(assessment_id: str, db: Session = Depends(get_db)):
    return engine.state_view(_get_assessment(db, assessment_id))


@app.post("/api/assessments/{assessment_id}/{phase}/start")
def start_section(assessment_id: str, phase: str, db: Session = Depends(get_db)):
    """Plan the section and write its first question."""
    assessment = _get_assessment(db, assessment_id)
    engine.start_section(db, assessment, _phase(phase))
    return engine.state_view(assessment)


@app.post("/api/assessments/{assessment_id}/{phase}/answer")
def submit_answer(assessment_id: str, phase: str, payload: AnswerSubmit, db: Session = Depends(get_db)):
    """Grade the current question; the next one is written from this answer."""
    assessment = _get_assessment(db, assessment_id)
    engine.submit_answer(db, assessment, _phase(phase), payload.question_id, payload.answer)
    return engine.state_view(assessment)


@app.post("/api/assessments/{assessment_id}/{phase}/next")
def next_question(assessment_id: str, phase: str, db: Session = Depends(get_db)):
    """Retry preparing the next question after a failure (answer already graded)."""
    assessment = _get_assessment(db, assessment_id)
    engine.advance(db, assessment, _phase(phase))
    return engine.state_view(assessment)


@app.get("/api/assessments/{assessment_id}/report")
def get_report(assessment_id: str, db: Session = Depends(get_db)):
    assessment = _get_assessment(db, assessment_id)
    if assessment.report is None:
        raise HTTPException(status_code=409, detail="التقرير غير جاهز بعد؛ أكمل قسمي التقييم أولًا.")
    return {
        **journey.localize_steps(assessment.report, request_lang.get()),
        "learning_progress": assessment.learning_progress or {},
        "reassessment": reassessment.eligibility(db, assessment),
        "lessons": {
            row.competency_id: {"completed": row.completed, "style": row.style}
            for row in db.scalars(select(Lesson).where(Lesson.assessment_pk == assessment.id).order_by(Lesson.id))
        },
    }


@app.post("/api/assessments/{assessment_id}/reassessment", status_code=status.HTTP_201_CREATED)
def start_reassessment(assessment_id: str, db: Session = Depends(get_db)):
    """After the learning journey: an independent reassessment of the journey's gaps."""
    child = reassessment.create(db, _get_assessment(db, assessment_id))
    return engine.state_view(child)


@app.get("/api/assessments/{assessment_id}/review")
def get_review(assessment_id: str, db: Session = Depends(get_db)):
    assessment = _get_assessment(db, assessment_id)
    if assessment.status != "completed":
        raise HTTPException(status_code=409, detail="مراجعة الأسئلة متاحة بعد اكتمال التقييم فقط.")
    return engine.review_view(assessment)


@app.put("/api/assessments/{assessment_id}/questions/{question_id}/review")
def review_question(assessment_id: str, question_id: str, payload: QuestionReviewIn, db: Session = Depends(get_db)):
    """Record a reviewer's judgement of a generated question's quality."""
    assessment = _get_assessment(db, assessment_id)
    if assessment.status != "completed":
        raise HTTPException(status_code=409, detail="تقييم جودة الأسئلة متاح بعد اكتمال التقييم فقط.")
    question = db.scalar(
        select(Question).where(Question.assessment_pk == assessment.id, Question.question_id == question_id.upper())
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    question.review_rating = payload.rating
    question.review_note = payload.note or None
    db.commit()
    return {"question_id": question.question_id, "review_rating": question.review_rating, "review_note": question.review_note}


# ---------------------------------------------------------------------------
# Learning activities (الرحلة التعليمية)
# ---------------------------------------------------------------------------

def _get_activity(db: Session, activity_id: str) -> LearningActivity:
    activity = db.scalar(select(LearningActivity).where(LearningActivity.activity_id == activity_id.strip().upper()))
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


def _is_hunter(activity: LearningActivity) -> bool:
    return activity.activity_type == "gap_hunter"


def _activity_view(activity: LearningActivity) -> dict:
    return gap_hunter.view(activity) if _is_hunter(activity) else activity_core.view(activity)


@app.post("/api/assessments/{assessment_id}/activities", status_code=status.HTTP_201_CREATED)
def start_activity(assessment_id: str, payload: ActivityCreate, db: Session = Depends(get_db)):
    """Start (or resume) an activity for one gap; generates the mission card and level 1."""
    assessment = _get_assessment(db, assessment_id)
    check_available(payload.activity_type)
    competency_id = payload.competency_id.upper()
    if payload.activity_type == "gap_hunter":
        activity = gap_hunter.start(db, assessment, competency_id)
    else:
        activity = activity_core.start(db, assessment, competency_id, payload.activity_type)
    return _activity_view(activity)


@app.get("/api/activities/{activity_id}")
def get_activity(activity_id: str, db: Session = Depends(get_db)):
    return _activity_view(_get_activity(db, activity_id))


@app.post("/api/activities/{activity_id}/action")
def activity_action(activity_id: str, payload: ActivityAction, db: Session = Depends(get_db)):
    """One move in escape room / work challenge / shadow / teach others."""
    activity = _get_activity(db, activity_id)
    if _is_hunter(activity):
        raise HTTPException(status_code=422, detail="Use /mark and /justify for Gap Hunter")
    outcome = activity_core.act(db, activity, payload.action, payload.payload)
    return {"outcome": outcome, "activity": activity_core.view(activity)}


@app.post("/api/activities/{activity_id}/mark")
def hunt_mark(activity_id: str, payload: HuntMark, db: Session = Depends(get_db)):
    activity = _get_activity(db, activity_id)
    outcome = gap_hunter.mark(db, activity, payload.line_index, payload.category)
    return {"outcome": outcome, "activity": gap_hunter.view(activity)}


@app.post("/api/activities/{activity_id}/justify")
def hunt_justify(activity_id: str, payload: HuntJustify, db: Session = Depends(get_db)):
    activity = _get_activity(db, activity_id)
    outcome = gap_hunter.justify(db, activity, payload.line_index, payload.explanation, payload.fix)
    return {"outcome": outcome, "activity": gap_hunter.view(activity)}


@app.post("/api/activities/{activity_id}/hint")
def activity_hint(activity_id: str, db: Session = Depends(get_db)):
    activity = _get_activity(db, activity_id)
    outcome = gap_hunter.hint(db, activity) if _is_hunter(activity) else activity_core.hint(db, activity)
    return {"outcome": outcome, "activity": _activity_view(activity)}


@app.post("/api/activities/{activity_id}/finish-level")
def activity_finish_level(activity_id: str, db: Session = Depends(get_db)):
    activity = _get_activity(db, activity_id)
    if _is_hunter(activity):
        gap_hunter.finish_level(db, activity.assessment, activity)
    else:
        activity_core.finish_level(db, activity.assessment, activity)
    return _activity_view(activity)


@app.post("/api/activities/{activity_id}/review-lesson")
def review_lesson(activity_id: str, db: Session = Depends(get_db)):
    """«📖 راجع الشرح» from inside an activity: free (unlike hints), and recorded as behavior."""
    activity = _get_activity(db, activity_id)
    current = lesson.current(db, activity.assessment, activity.competency_id)
    if current is None:
        raise HTTPException(status_code=404, detail="لا يوجد شرح لهذه الفجوة بعد.")
    current.reviews += 1
    if activity.status == "playing" and activity.levels:
        record_event(db, activity, activity.levels[-1], "review_lesson", details={"lesson_id": current.lesson_id})
    db.commit()
    return lesson.view(current)


# ---------------------------------------------------------------------------
# Lessons (📖 the briefing before an activity)
# ---------------------------------------------------------------------------

def _get_lesson(db: Session, lesson_id: str) -> Lesson:
    found = db.scalar(select(Lesson).where(Lesson.lesson_id == lesson_id.strip().upper()))
    if found is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return found


@app.get("/api/assessments/{assessment_id}/lessons/{competency_id}")
def lesson_status(assessment_id: str, competency_id: str, db: Session = Depends(get_db)):
    return lesson.status(db, _get_assessment(db, assessment_id), competency_id.upper())


@app.post("/api/assessments/{assessment_id}/lessons/{competency_id}", status_code=status.HTTP_201_CREATED)
def create_lesson(assessment_id: str, competency_id: str, payload: LessonCreate, db: Session = Depends(get_db)):
    created = lesson.create(db, _get_assessment(db, assessment_id), competency_id.upper(), payload.style)
    return lesson.view(created)


@app.post("/api/lessons/{lesson_id}/final-step")
def lesson_final_step(lesson_id: str, payload: LessonAnswer, db: Session = Depends(get_db)):
    return lesson.answer_final_step(db, _get_lesson(db, lesson_id), payload.choice)


@app.post("/api/lessons/{lesson_id}/check")
def lesson_check(lesson_id: str, payload: LessonAnswer, db: Session = Depends(get_db)):
    return lesson.answer_check(db, _get_lesson(db, lesson_id), payload.index, payload.choice)


@app.post("/api/lessons/{lesson_id}/complete")
def lesson_complete(lesson_id: str, db: Session = Depends(get_db)):
    found = _get_lesson(db, lesson_id)
    lesson.complete(db, found)
    return lesson.view(found)


# Serve the frontend from the same origin (mounted last so /api routes win).
app.mount("/", StaticFiles(directory=config.PROJECT_ROOT / "frontend", html=True), name="frontend")
