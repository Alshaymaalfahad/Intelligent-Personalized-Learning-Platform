"""Database tables."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Trainee(Base):
    """Trainee profile. Deliberately has no self-reported skills or experience
    level: those are what the assessment measures."""

    __tablename__ = "trainees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Public ID such as "TR-0001", derived from `id` after insert.
    trainee_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    specialization: Mapped[str] = mapped_column(String(100))
    interests: Mapped[list[str]] = mapped_column(JSON)
    additional_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_status: Mapped[str] = mapped_column(String(20), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assessments: Mapped[list["Assessment"]] = relationship(back_populates="trainee")


class Assessment(Base):
    """One assessment attempt: an adaptive skills section, then an adaptive knowledge
    section planned from the skill results, then the gap report. See assessment_engine."""

    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    trainee_pk: Mapped[int] = mapped_column(ForeignKey("trainees.id"))
    # "initial" assessment, or a "reassessment" after the learning journey of `parent_pk`.
    kind: Mapped[str | None] = mapped_column(String(20), nullable=True, default="initial")
    parent_pk: Mapped[int | None] = mapped_column(ForeignKey("assessments.id"), nullable=True)
    # Reassessment only: per-competency training history and behavior signals that steer the questions.
    reassessment_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="created")
    ai_model: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # What the AI decided to measure, e.g. [{"competency_id": "SK-01", "name": ...}]
    skill_blueprint: Mapped[list | None] = mapped_column(JSON, nullable=True)
    knowledge_blueprint: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # How the skill results shaped the knowledge section (AI explanation).
    adaptation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    skill_results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Learning journey progress per competency: {"SK-03": {"baseline": 40, "current": 78, "status": "closed", …}}
    learning_progress: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    trainee: Mapped[Trainee] = relationship(back_populates="assessments")
    parent: Mapped["Assessment | None"] = relationship(remote_side="Assessment.id")
    activities: Mapped[list["LearningActivity"]] = relationship(back_populates="assessment")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="assessment", order_by="Question.position", cascade="all, delete-orphan"
    )

    def phase_questions(self, phase: str) -> list["Question"]:
        return [q for q in self.questions if q.phase == phase]


class Question(Base):
    """A generated question plus the trainee's answer and its grading.

    Reference answer, correct option and rubric stay on the server: they are
    never included in what the browser receives before the section is graded.
    """

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_pk: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    question_id: Mapped[str] = mapped_column(String(10))  # SQ-01.. / KQ-01..
    phase: Mapped[str] = mapped_column(String(10))  # "skill" | "knowledge"
    position: Mapped[int] = mapped_column(Integer)

    competency_id: Mapped[str] = mapped_column(String(10))
    question_type: Mapped[str] = mapped_column(String(20))
    bloom_level: Mapped[str] = mapped_column(String(20))
    difficulty: Mapped[int] = mapped_column(Integer)
    learning_objective: Mapped[str] = mapped_column(Text)
    question_text: Mapped[str] = mapped_column(Text)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    correct_option_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Ordering questions: displayed option indices in the correct sequence.
    correct_order: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    reference_answer: Mapped[str] = mapped_column(Text)
    scoring_rubric: Mapped[list] = mapped_column(JSON, default=list)
    max_score: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    # Why the adaptive selector chose this target (Arabic) — shown only in the review.
    adaptation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Trainee answer: option index (int), free text (str), or an order (list of option indices).
    trainee_answer: Mapped[int | str | list | None] = mapped_column(JSON, nullable=True)
    earned_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    grading_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    grading_details: Mapped[list | None] = mapped_column(JSON, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Reviewer's judgement of the question itself (for testing question quality).
    review_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="questions")

    @property
    def is_open(self) -> bool:
        return self.question_type == "open_ended"

    @property
    def is_ordering(self) -> bool:
        return self.question_type == "ordering"


class LearningActivity(Base):
    """One play-through of a gamified learning activity for one gap.

    `levels` holds the generated content AND the play state of every level; the
    answer key inside it never leaves the server until the item is found or revealed.
    """

    __tablename__ = "learning_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    assessment_pk: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    competency_id: Mapped[str] = mapped_column(String(10))
    activity_type: Mapped[str] = mapped_column(String(30))
    # created → generating → playing ⇄ generating … → completed
    status: Mapped[str] = mapped_column(String(20), default="created")
    current_level: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    false_alarms: Mapped[int] = mapped_column(Integer, default=0)
    mission: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    levels: Mapped[list] = mapped_column(JSON, default=list)
    badges: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    assessment: Mapped[Assessment] = relationship(back_populates="activities")


class LearningEvent(Base):
    """One attempt inside a learning activity — the raw behavior record.

    Per the operational concept: task, target competency, result, error type,
    attempt number, hints so far, approximate time, justification, and the next
    decision the system took.
    """

    __tablename__ = "learning_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_pk: Mapped[int] = mapped_column(ForeignKey("learning_activities.id"), index=True)
    competency_id: Mapped[str] = mapped_column(String(10))
    level: Mapped[int] = mapped_column(Integer)
    # mark_found | false_alarm | justify | hint | finish_level
    event_type: Mapped[str] = mapped_column(String(20))
    correct: Mapped[bool | None] = mapped_column(nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer)  # nth action in this level
    hints_so_far: Mapped[int] = mapped_column(Integer)
    seconds_since_previous: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    system_decision: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Lesson(Base):
    """The briefing before an activity for one gap: why it matters → I explain →
    we do it together → quick check. Its style is chosen by the trainee; how well
    each style works is tracked to suggest it for the next gaps."""

    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lesson_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    assessment_pk: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    competency_id: Mapped[str] = mapped_column(String(10))
    depth: Mapped[str] = mapped_column(String(20))  # compound | application | shallow | mastery
    style: Mapped[str] = mapped_column(String(20))  # brief | story | visual | interactive
    content: Mapped[dict] = mapped_column(JSON)
    # Answers are recorded (first try) but never graded — they only feed the style signal.
    final_step_answer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    check_answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    completed: Mapped[bool] = mapped_column(default=False)
    reviews: Mapped[int] = mapped_column(Integer, default=0)  # «📖 راجع الشرح» from inside an activity
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
