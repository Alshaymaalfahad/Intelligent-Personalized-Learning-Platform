"""Builds the prompts, calls the AI, and checks every output.

Two kinds of calls per section:
  - a plan: which skills / knowledge areas to measure (hidden from the trainee);
  - one question at a time, written for a target chosen by adaptive_selector
    and informed by the trainee's previous answers.

Nothing the model returns is trusted as-is: if it breaks a rule, the list of
problems is sent back to the model for one corrected attempt.
"""

import json
import logging
import random
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, TypeVar

from pydantic import BaseModel

from .adaptive_selector import QUESTIONS_PER_SECTION, Target, passed
from .ai_client import AIOutputInvalid, generate_structured
from .i18n import LANGUAGE_RULES, TRUE_FALSE_OPTIONS as TF_OPTIONS, lang_of, strip_enumerator
from .schemas import KnowledgePlanOutput, QuestionDraft, SkillPlanOutput

log = logging.getLogger("question_generator")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

SKILL_KINDS = {"hard": 3, "soft": 2}
SKILL_COUNT = sum(SKILL_KINDS.values())
KNOWLEDGE_AREA_RANGE = (4, 5)
CHOICE_OPTION_COUNT = 4
ORDERING_STEPS = (4, 5)
# Keep questions quick to read and answer (~1 minute).
MAX_QUESTION_CHARS = 450
MAX_OPTION_CHARS = 160
MAX_CODE_LINES = 12
RUBRIC_CRITERIA_RANGE = (2, 4)
RUBRIC_POINTS_RANGE = (1, 2)
DUPLICATE_SIMILARITY = 0.85
MAX_ATTEMPTS = 2
BANNED_OPTIONS = ("all of the above", "none of the above", "جميع ما سبق", "كل ما سبق", "لا شيء مما سبق")

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def render_prompt(template_name: str, *, lang: str = "en", **values: str) -> str:
    """Fill {{placeholders}}; `lang` sets the output-language rule and True/False wording."""
    values.setdefault("language_rule", LANGUAGE_RULES[lang])
    values.setdefault("tf_options", json.dumps(TF_OPTIONS[lang], ensure_ascii=False))
    text = (PROMPTS_DIR / template_name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    leftover = re.findall(r"\{\{(\w+)\}\}", text)
    if leftover:
        raise ValueError(f"unfilled placeholders in {template_name}: {leftover}")
    return text


def _untrusted(text: str | None) -> str:
    """Neutralize attempts to close the wrapping tag from inside trainee text."""
    if not text:
        return "(none)"
    return text.replace("<", "‹").replace(">", "›")


def _trainee_values(trainee) -> dict[str, str]:
    return {
        "specialization": trainee.specialization,
        "interests": ", ".join(trainee.interests),
        "additional_message": _untrusted(trainee.additional_message),
    }


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Generation with one corrective retry
# ---------------------------------------------------------------------------

def _correction_block(problems: list[str]) -> str:
    lines = "\n".join(f"- {p}" for p in problems[:20])
    return (
        "\n\n# Correction required\n"
        "Your previous output was rejected by the application's validator for these reasons:\n"
        f"{lines}\n"
        "Produce a complete new output that fixes all of them while following every rule above."
    )


def generate_validated(
    prompt: str, output_model: type[T], validate: Callable[[T], list[str]], *, task: str, effort: str | None = None
) -> T:
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        full_prompt = prompt + (_correction_block(problems) if problems else "")
        try:
            kwargs = {"effort": effort} if effort else {}
            output = generate_structured(full_prompt, output_model, task=task, **kwargs)
        except AIOutputInvalid as e:
            problems = e.problems
        else:
            problems = validate(output)
            if not problems:
                return output
        log.warning("[%s] attempt %d rejected: %s", task, attempt, problems)
    raise AIOutputInvalid(problems)


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

def validate_skill_plan(out: SkillPlanOutput) -> list[str]:
    problems = []
    ids = [s.competency_id for s in out.skills]
    expected = [f"SK-{i:02d}" for i in range(1, SKILL_COUNT + 1)]
    if ids != expected:
        problems.append(f"skills must be exactly {SKILL_COUNT} with ids {expected} in order; got {ids}.")
    for s in out.skills:
        if not s.name.strip() or not s.description.strip():
            problems.append(f"skill {s.competency_id}: name and description are required.")
    if len({s.name.strip().casefold() for s in out.skills}) != len(out.skills):
        problems.append("skill names must be distinct.")
    kinds = {k: sum(1 for s in out.skills if s.skill_kind == k) for k in SKILL_KINDS}
    if kinds != SKILL_KINDS:
        problems.append(f"skills must be exactly {SKILL_KINDS['hard']} hard and {SKILL_KINDS['soft']} soft; got {kinds}.")
    return problems


def validate_knowledge_plan(out: KnowledgePlanOutput, skill_ids: set[str]) -> list[str]:
    problems = []
    ids = [a.competency_id for a in out.knowledge_areas]
    lo, hi = KNOWLEDGE_AREA_RANGE
    if not lo <= len(ids) <= hi or ids != [f"KN-{i:02d}" for i in range(1, len(ids) + 1)]:
        problems.append(f"knowledge_areas must be {lo}-{hi} areas with ids KN-01, KN-02, … in order; got {ids}.")
    for a in out.knowledge_areas:
        if not a.name.strip() or not a.description.strip():
            problems.append(f"knowledge area {a.competency_id}: name and description are required.")
        unknown = [s for s in a.related_skill_ids if s not in skill_ids]
        if unknown:
            problems.append(f"knowledge area {a.competency_id}: related_skill_ids {unknown} do not exist.")
    if not out.adaptation_summary.strip():
        problems.append("adaptation_summary is empty.")
    return problems


def plan_skills(trainee) -> SkillPlanOutput:
    prompt = render_prompt("skill_plan.txt", lang=lang_of(trainee), **_trainee_values(trainee))
    return generate_validated(prompt, SkillPlanOutput, validate_skill_plan, task="skill_plan")


def plan_knowledge(trainee, skill_blueprint: list[dict], skill_results: list[dict]) -> KnowledgePlanOutput:
    results_by_id = {r["competency_id"]: r for r in skill_results}
    summary = [
        {
            "competency_id": s["competency_id"],
            "skill": s["name"],
            "kind": s["skill_kind"],
            "importance": s["importance"],
            "score_percent": results_by_id[s["competency_id"]]["score"],
            "status": results_by_id[s["competency_id"]]["status"],
            "questions": [
                {"difficulty": e["difficulty"], "type": e["question_type"], "result_percent": e["result_percent"]}
                for e in results_by_id[s["competency_id"]]["evidence"]
            ],
        }
        for s in skill_blueprint
    ]
    prompt = render_prompt("knowledge_plan.txt", lang=lang_of(trainee), **_trainee_values(trainee), skill_results=_json(summary))
    skill_ids = {s["competency_id"] for s in skill_blueprint}
    return generate_validated(
        prompt, KnowledgePlanOutput, lambda out: validate_knowledge_plan(out, skill_ids), task="knowledge_plan"
    )


# ---------------------------------------------------------------------------
# One adaptive question
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _is_duplicate(text: str, previous_texts: list[str]) -> bool:
    norm = _normalize_text(text)
    return any(SequenceMatcher(None, norm, _normalize_text(p)).ratio() >= DUPLICATE_SIMILARITY for p in previous_texts)


def validate_question(q: QuestionDraft, target: Target, previous_texts: list[str]) -> list[str]:
    problems = []
    if q.question_type not in target.allowed_types:
        problems.append(f"question_type must be one of {target.allowed_types}, got '{q.question_type}'.")
    for name in ("question_text", "learning_objective", "reference_answer", "rationale"):
        if not getattr(q, name).strip():
            problems.append(f"{name} is empty.")

    if len(q.question_text) > MAX_QUESTION_CHARS:
        problems.append(f"question_text is {len(q.question_text)} characters; keep it under {MAX_QUESTION_CHARS} (short and quick to read).")
    if len(q.code_snippet.strip().splitlines()) > MAX_CODE_LINES:
        problems.append(f"code_snippet must be at most {MAX_CODE_LINES} lines.")

    if q.question_type == "open_ended":
        if q.options:
            problems.append("open_ended questions must have no options.")
        lo, hi = RUBRIC_CRITERIA_RANGE
        if not lo <= len(q.scoring_rubric) <= hi:
            problems.append(f"open_ended rubric needs {lo}-{hi} criteria.")
        if any(not c.criterion.strip() or not RUBRIC_POINTS_RANGE[0] <= c.points <= RUBRIC_POINTS_RANGE[1] for c in q.scoring_rubric):
            problems.append(f"each rubric criterion needs text and {RUBRIC_POINTS_RANGE[0]}-{RUBRIC_POINTS_RANGE[1]} points.")
    else:
        options = [o.strip() for o in q.options]
        if q.question_type == "ordering":
            lo, hi = ORDERING_STEPS
            if not lo <= len(options) <= hi:
                problems.append(f"ordering needs {lo}-{hi} steps listed in the correct order, got {len(options)}.")
        else:
            expected = 2 if q.question_type == "true_false" else CHOICE_OPTION_COUNT
            if len(options) != expected:
                problems.append(f"{q.question_type} needs exactly {expected} options, got {len(options)}.")
            if not 0 <= q.correct_option_index < len(options):
                problems.append(f"correct_option_index {q.correct_option_index} is out of range.")
        if any(not o for o in options) or len({o.casefold() for o in options}) != len(options):
            problems.append("options must be non-empty and distinct.")
        if any(len(o) > MAX_OPTION_CHARS for o in options):
            problems.append(f"each option must be under {MAX_OPTION_CHARS} characters.")
        if any(b in o.casefold() for o in options for b in BANNED_OPTIONS):
            problems.append("'all/none of the above' options are not allowed.")

    if q.question_text.strip() and _is_duplicate(q.question_text, previous_texts):
        problems.append("The question duplicates or rephrases a question already asked. Write a different one.")
    return problems


def normalize_question(q: QuestionDraft, target: Target, correct_index: int, lang: str = "en") -> dict:
    """Clean a validated draft into the fields stored on models.Question.

    For 4-option questions the correct option is moved to `correct_index`, so the
    position of the right answer is balanced by the server, not left to the model.
    Ordering steps arrive in the correct order and are shuffled for display.
    """
    is_open = q.question_type == "open_ended"
    rubric = [{"criterion": c.criterion.strip(), "points": c.points} for c in q.scoring_rubric] if is_open else []
    correct_order = None
    if is_open:
        options, correct = [], None
    elif q.question_type == "ordering":
        steps = [strip_enumerator(o) for o in q.options]
        display = list(range(len(steps)))
        while display == sorted(display):
            random.shuffle(display)
        options = [steps[i] for i in display]
        correct_order = [display.index(i) for i in range(len(steps))]
        correct = None
    elif q.question_type == "true_false":
        options, correct = list(TF_OPTIONS[lang]), q.correct_option_index
    else:
        options = [o.strip() for o in q.options]
        correct = correct_index
        options[q.correct_option_index], options[correct] = options[correct], options[q.correct_option_index]
    return {
        "competency_id": target.competency_id,
        "question_type": q.question_type,
        "bloom_level": target.bloom_level,
        "difficulty": target.difficulty,
        "learning_objective": q.learning_objective.strip(),
        "question_text": q.question_text.strip(),
        "code_snippet": q.code_snippet.strip() or None,
        "options": options,
        "correct_option_index": correct,
        "correct_order": correct_order,
        "reference_answer": q.reference_answer.strip(),
        "scoring_rubric": rubric,
        "max_score": float(sum(c["points"] for c in rubric)) if is_open else 1.0,
        "rationale": q.rationale.strip(),
        "adaptation_reason": target.reason,
        "adaptation_code": target.reason_code,
    }


def _evidence(q) -> dict:
    item = {
        "question": q.question_text,
        "type": q.question_type,
        "bloom_level": q.bloom_level,
        "difficulty": q.difficulty,
        "result": "correct" if passed(q) else "incorrect",
    }
    if q.is_open:
        item["score"] = f"{q.earned_score:g}/{q.max_score:g}"
        item["grader_feedback"] = q.feedback  # never the raw answer text (untrusted)
    elif q.is_ordering:
        item["correct_order"] = [q.options[i] for i in q.correct_order]
        item["trainee_order"] = [q.options[i] for i in q.trainee_answer]
    else:
        item["correct_option"] = q.options[q.correct_option_index]
        item["trainee_chose"] = q.options[q.trainee_answer]
    return item


def _balanced_choice(counts: dict[int, int]) -> int:
    fewest = min(counts.values())
    return random.choice([i for i, c in counts.items() if c == fewest])


def write_question(
    trainee,
    phase: str,
    target: Target,
    competency: dict,
    all_questions: list,
    position: int,
    *,
    total: int = QUESTIONS_PER_SECTION,
    extra_history: list[str] | None = None,
    reassessment_context: str | None = None,
) -> dict:
    """Generate, validate and normalize one question for `target`.

    `extra_history` (earlier assessments' questions) is never repeated;
    `reassessment_context` steers a reassessment question with the training behavior."""
    section = [q for q in all_questions if q.phase == phase]
    index_counts = {i: 0 for i in range(CHOICE_OPTION_COUNT)}
    tf_counts = {0: 0, 1: 0}
    for q in section:
        if q.question_type == "true_false":
            tf_counts[q.correct_option_index] += 1
        elif q.correct_option_index is not None and q.correct_option_index < CHOICE_OPTION_COUNT:
            index_counts[q.correct_option_index] += 1
    correct_index = _balanced_choice(index_counts)
    tf_correct = _balanced_choice(tf_counts)

    previous_texts = [q.question_text for q in all_questions] + (extra_history or [])
    values = {
        **_trainee_values(trainee),
        "position": position,
        "total": total,
        "difficulty": target.difficulty,
        "bloom_level": target.bloom_level,
        "question_type": target.allowed_types[0],
        "adaptation_reason": target.reason,
        "previous_on_competency": _json([_evidence(q) for q in target.previous_on_competency]) if target.previous_on_competency else "(none — this is the first question on it)",
        "history": _json([t[:300] for t in previous_texts]) if previous_texts else "(none)",
        "reassessment_context": reassessment_context or "(not a reassessment)",
        "correct_index_hint": correct_index,
        "tf_hint": TF_OPTIONS[lang_of(trainee)][tf_correct],
    }
    info = {"name": competency["name"], "description": competency["description"]}
    if phase == "skill":
        prompt = render_prompt("skill_question.txt", lang=lang_of(trainee), **values, skill=_json(info))
    else:
        prompt = render_prompt("knowledge_question.txt", lang=lang_of(trainee), **values, area=_json(info))

    draft = generate_validated(
        prompt, QuestionDraft, lambda q: validate_question(q, target, previous_texts), task=f"{phase}_question_{position}"
    )
    return normalize_question(draft, target, correct_index, lang_of(trainee))
