"""Shapes of data accepted and returned by the API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .catalog import find_specialization

MAX_INTERESTS = 6
MAX_INTEREST_LENGTH = 60
MAX_MESSAGE_LENGTH = 500


class TraineeCreate(BaseModel):
    # extra="forbid": the profile must not accept self-reported skills/levels.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    language: Literal["en", "ar"] = "en"
    specialization: str = Field(min_length=2, max_length=100)
    interests: list[str] = Field(min_length=1, max_length=MAX_INTERESTS)
    additional_message: str | None = Field(default=None, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            value = value.strip()
            if not value:
                continue
            if len(value) > MAX_INTEREST_LENGTH:
                raise ValueError(f"each interest must be at most {MAX_INTEREST_LENGTH} characters")
            if value.casefold() not in seen:
                seen.add(value.casefold())
                cleaned.append(value)
        if not cleaned:
            raise ValueError("select at least one interest")
        return cleaned

    @field_validator("additional_message")
    @classmethod
    def empty_message_to_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def normalize_catalog_names(self) -> "TraineeCreate":
        """Known specializations and their suggested interests are normalized to the
        catalog spelling; any other interest is a trainee-added area, kept as typed."""
        spec = find_specialization(self.specialization)
        if spec is None:
            return self
        self.specialization = spec["name"]
        known = {}
        for i in spec["interests"]:
            known[i["name"].casefold()] = i["name"]
            known[i["label_ar"].casefold()] = i["name"]
        normalized: list[str] = []
        for interest in self.interests:
            value = known.get(interest.casefold(), interest)
            if value not in normalized:
                normalized.append(value)
        self.interests = normalized
        return self


class TraineeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trainee_id: str
    language: str | None
    specialization: str
    interests: list[str]
    additional_message: str | None
    profile_status: str


# ---------------------------------------------------------------------------
# AI output (structured output schemas). Loose on purpose: the detailed rules
# are checked in question_generator.validate_* so that violations can be fed
# back to the model as a readable list on retry.
# ---------------------------------------------------------------------------

QuestionType = Literal["multiple_choice", "true_false", "scenario", "error_detection", "ordering", "open_ended"]


class RubricCriterion(BaseModel):
    criterion: str
    points: int


class QuestionDraft(BaseModel):
    """One question written by the AI. Competency, difficulty and Bloom level are
    decided by the adaptive selector, so they are not part of the AI output."""

    question_type: QuestionType
    learning_objective: str
    question_text: str
    code_snippet: str = Field(description="Code/query/config/log shown with the question; empty string if none")
    options: list[str] = Field(
        description="Answer options; for ordering: the steps IN THE CORRECT ORDER; empty list for open_ended"
    )
    correct_option_index: int = Field(description="0-based index of the correct option; -1 for ordering and open_ended")
    reference_answer: str
    scoring_rubric: list[RubricCriterion] = Field(description="Only for open_ended; empty list otherwise")
    rationale: str


class SkillDefinition(BaseModel):
    competency_id: str
    skill_kind: Literal["hard", "soft"]
    name: str
    description: str
    importance: Literal[1, 2, 3]
    linked_interest: str


class SkillPlanOutput(BaseModel):
    skills: list[SkillDefinition]


class KnowledgeArea(BaseModel):
    competency_id: str
    name: str
    description: str
    importance: Literal[1, 2, 3]
    related_skill_ids: list[str]
    selection_reason: str


class KnowledgePlanOutput(BaseModel):
    adaptation_summary: str
    knowledge_areas: list[KnowledgeArea]


class CriterionScore(BaseModel):
    criterion: str
    awarded: int
    justification: str


class OpenAnswerEvaluation(BaseModel):
    question_id: str
    criteria_scores: list[CriterionScore]
    confidence: float = Field(description="0.0 to 1.0")
    feedback: str


class OpenAnswerEvaluationOutput(BaseModel):
    evaluations: list[OpenAnswerEvaluation]


# ---------------------------------------------------------------------------
# Assessment API
# ---------------------------------------------------------------------------

MAX_OPEN_ANSWER_LENGTH = 3000


class AssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    trainee_id: str = Field(min_length=1, max_length=20)


class AnswerSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(max_length=10)
    # Option index (choice), text (open-ended), or the displayed indices in the chosen order (ordering).
    answer: int | str | list[int]

    @field_validator("answer")
    @classmethod
    def limit_text(cls, value: int | str | list[int]) -> int | str | list[int]:
        if isinstance(value, list) and len(value) > 10:
            raise ValueError("too many items")
        if isinstance(value, str):
            value = value.strip()
            if len(value) > MAX_OPEN_ANSWER_LENGTH:
                raise ValueError(f"answer must be at most {MAX_OPEN_ANSWER_LENGTH} characters")
        return value


class QuestionReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rating: Literal["good", "needs_work", "bad"]
    note: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# Learning activities — Gap Hunter (صياد الفجوات)
# ---------------------------------------------------------------------------

class HuntError(BaseModel):
    line_index: int = Field(description="0-based index of the line that contains this error")
    related_lines: list[int] = Field(
        description="Other lines that are part of the same mistake (e.g. the original of a duplicate record); clicking them also counts. Usually empty."
    )
    category: str = Field(description="One of the level's categories")
    explanation_options: list[str] = Field(description="3 options for WHY it is an error")
    correct_explanation: int = Field(description="0-based index of the correct explanation")
    fix_options: list[str] = Field(description="3 options for the fix")
    correct_fix: int = Field(description="0-based index of the correct fix")
    hint_1: str = Field(description="Vague hint: the area to look at, without giving the answer")
    hint_2: str = Field(description="More precise hint: what to pay attention to")


class HuntLevel(BaseModel):
    mentor_message: str
    artifact_title: str
    artifact_kind: Literal["table", "code", "text", "config", "log"]
    lines: list[str] = Field(description="The artifact, one item per line; for tables the first line is the header and cells are separated by ' | '")
    categories: list[str] = Field(description="4-5 error categories the trainee picks from")
    errors: list[HuntError]
    line_notes: list[str] = Field(
        description="One short Arabic note per line explaining why that line is CORRECT (shown if the trainee wrongly flags it); empty string for mistake lines"
    )


class HuntMission(BaseModel):
    title: str
    story: str
    goal: str
    win_condition: str


class HuntFirstLevelOutput(BaseModel):
    mission: HuntMission
    level: HuntLevel


class HuntNextLevelOutput(BaseModel):
    level: HuntLevel


class ActivityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competency_id: str = Field(max_length=10)
    activity_type: Literal["escape_room", "gap_hunter", "work_challenge", "shadow", "teach_others"]


class HuntMark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_index: int = Field(ge=0, le=100)
    category: str = Field(max_length=120)


class HuntJustify(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_index: int = Field(ge=0, le=100)
    explanation: int = Field(ge=0, le=10)
    fix: int = Field(ge=0, le=10)


class ActivityAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["answer", "justify", "submit", "predict", "submit_steps", "explain", "final_lesson"]
    payload: dict = Field(default_factory=dict)


class LessonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: Literal["brief", "story", "visual", "interactive"]


class LessonAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: int = Field(ge=0, le=10)
    index: int = Field(default=0, ge=0, le=5)


class JourneySelection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    skill_id: str = Field(min_length=2, max_length=10)
    level: Literal["new", "some", "deep"] | None = None
    later: bool = False


class JourneyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selections: list[JourneySelection] = Field(min_length=1, max_length=60)


class JourneyCreate(JourneyUpdate):
    trainee_id: str = Field(min_length=1, max_length=40)
    # True: sign up with this new ID. False: a returning trainee starting their next round.
    new_trainee: bool = False
    language: Literal["en", "ar"] = "en"
