"""Structured-output schemas for the learning activities built on activity_core.

Loose on purpose (like schemas.py): detailed rules are checked by each activity's
validate_* function, so violations can be sent back to the model for one retry.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Mission(BaseModel):
    title: str
    story: str = Field(description="2-3 short Arabic sentences: a realistic work situation with a little urgency")
    goal: str
    win_condition: str


# ---------------------------------------------------------------------------
# 🔐 Escape room
# ---------------------------------------------------------------------------

class EscapeDoor(BaseModel):
    mentor_message: str
    door_title: str
    scenario: str
    artifact_kind: Literal["none", "table", "code", "text"]
    artifact_lines: list[str] = Field(description="Evidence shown with the door; empty list when artifact_kind is none")
    challenge_type: Literal["choice", "multi_select"]
    question: str
    options: list[str]
    correct_options: list[int] = Field(description="0-based indices; exactly 1 for choice, 2-3 for multi_select")
    option_consequences: list[str] = Field(description="Same length as options: what happens next if this option is chosen")
    justification_question: str
    justification_options: list[str]
    correct_justification: int
    clue_sheet: str = Field(description="Short explanation of the concept needed for THIS door only")
    hints: list[str] = Field(description="2 progressive hints")


class EscapeFirstOutput(BaseModel):
    mission: Mission
    door: EscapeDoor


class EscapeNextOutput(BaseModel):
    door: EscapeDoor


# ---------------------------------------------------------------------------
# 🧩 Work challenge
# ---------------------------------------------------------------------------

class WorkCriterion(BaseModel):
    criterion: str
    points: int = Field(description="1-3")


class WorkTask(BaseModel):
    mentor_message: str
    sender_name: str
    sender_role: str
    subject: str
    message: str = Field(description="The email/message the trainee receives")
    input_title: str
    input_lines: list[str] = Field(description="Material attached to the task (data, notes, code); may be empty")
    deliverable_instructions: str
    acceptance_criteria: list[WorkCriterion]
    hints: list[str] = Field(description="2 progressive hints")
    model_answer: str = Field(description="What a strong deliverable contains (never shown before submission)")


class WorkMission(Mission):
    job_title: str = Field(description="Arabic job title for the trainee's role, e.g. محلل نظم")


class WorkFirstOutput(BaseModel):
    mission: WorkMission
    task: WorkTask


class WorkNextOutput(BaseModel):
    task: WorkTask


class CriterionReview(BaseModel):
    criterion: str
    status: Literal["met", "partial", "missing"]
    comment: str


class WorkReview(BaseModel):
    criteria: list[CriterionReview]
    manager_feedback: str
    confidence: float = Field(description="0.0 to 1.0")


# ---------------------------------------------------------------------------
# 👥 Shadow / reverse shadow
# ---------------------------------------------------------------------------

class ShadowStep(BaseModel):
    step: str = Field(description="One short action the expert takes")
    why: str = Field(description="Why the expert does it")
    golden_practice: str = Field(description="Short reusable professional rule learned from this step")


class ShadowPause(BaseModel):
    step_index: int = Field(description="0-based index of the expert step the trainee must predict")
    distractors: list[str] = Field(description="2 plausible but worse next steps")
    hint: str


class ShadowLevel(BaseModel):
    mentor_message: str
    task_title: str
    situation: str
    artifact_lines: list[str] = Field(description="Material the expert works on; may be empty")
    expert_steps: list[ShadowStep]
    pauses: list[ShadowPause]
    distractor_steps: list[str] = Field(description="3 plausible but wrong or unnecessary steps")
    hints: list[str] = Field(description="2 progressive hints for doing the task")


class ShadowMission(Mission):
    expert_name: str = Field(description="Arabic name and role of the expert, e.g. م. خالد — مهندس برمجيات أول")


class ShadowFirstOutput(BaseModel):
    mission: ShadowMission
    level: ShadowLevel


class ShadowNextOutput(BaseModel):
    level: ShadowLevel


# ---------------------------------------------------------------------------
# 🎓 Teach others (سعود)
# ---------------------------------------------------------------------------

class TeachQuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct: int


class TeachLevel(BaseModel):
    mentor_message: str
    concept: str = Field(description="The concept this round is about")
    misconception: str = Field(description="Saud's wrong belief (for the boss: his remaining doubts)")
    saud_opening: str = Field(description="Saud's first message, stating the misconception naturally")
    key_points: list[str] = Field(description="3-4 points a good explanation must cover")
    hints: list[str] = Field(description="2 progressive hints")
    quiz: list[TeachQuizQuestion] = Field(description="Boss level only: Saud's 3-question test; empty list otherwise")


class TeachFirstOutput(BaseModel):
    mission: Mission
    level: TeachLevel


class TeachNextOutput(BaseModel):
    level: TeachLevel


class TeachTurn(BaseModel):
    covered_points: list[int] = Field(description="Indices of key points explained correctly so far in this round")
    accurate: bool = Field(description="False if the explanation contains a technically wrong statement")
    has_example: bool
    clarity: Literal["clear", "partly", "vague"]
    understanding: int = Field(description="Saud's understanding 0-100 after this message")
    saud_reply: str


class SaudAnswer(BaseModel):
    question_index: int
    chosen_option: int
    reasoning: str = Field(description="Saud's reasoning, citing what the trainee taught him")


class SaudQuizOutput(BaseModel):
    answers: list[SaudAnswer]
    saud_message: str


# ---------------------------------------------------------------------------
# 📖 Lesson (the briefing before an activity): why → I do → we do → quick check
# ---------------------------------------------------------------------------

class LessonSection(BaseModel):
    emoji: str = Field(description="One emoji for the section (used by the visual style)")
    heading: str
    body: str
    reveal_question: str = Field(description="Interactive style only: a question the trainee thinks about before revealing; empty otherwise")


class SolvedStep(BaseModel):
    step: str
    explanation: str


class CheckQuestion(BaseModel):
    question: str
    options: list[str]
    correct: int
    explanation: str = Field(description="Why the correct answer is right (and the tempting one wrong)")


class LessonContent(BaseModel):
    why_title: str
    why_story: str = Field(description="A short real incident showing the impact of this gap (at most ~50 words)")
    why_impact: str = Field(description="One line: what it cost")
    explanation_title: str
    sections: list[LessonSection]
    takeaways: list[str]
    example_problem: str
    example_lines: list[str] = Field(description="Material of the worked example; may be empty")
    example_steps: list[SolvedStep] = Field(description="The solved steps shown by the mentor")
    final_step_question: str = Field(description="The trainee completes the last step of the example")
    final_step_options: list[str]
    final_step_correct: int
    final_step_explanation: str
    check: list[CheckQuestion]
