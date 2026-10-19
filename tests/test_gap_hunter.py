"""Gap Hunter (صياد الفجوات) play-through with a fake AI."""

import re

import pytest
from fastapi.testclient import TestClient

from backend import question_generator
from backend.database import SessionLocal
from backend.main import app
from backend.models import LearningActivity
from backend.schemas import HuntError, HuntFirstLevelOutput, HuntLevel, HuntMission, HuntNextLevelOutput
from tests.test_assessment import FakeAI, _answer, _start

CATEGORIES = ["قيمة ناقصة", "تكرار", "صيغة خاطئة", "قيمة شاذة", "خطأ منطقي"]


def fake_level(count: int) -> HuntLevel:
    return HuntLevel(
        mentor_message="هيا نبدأ!",
        artifact_title="ملف عميل",
        artifact_kind="table",
        lines=["id | name | date"] + [f"{i} | row {i} | 2026-01-0{i % 9 + 1}" for i in range(1, 11)],
        line_notes=[""] + [f"السطر {i} سليم لأن…" for i in range(1, 11)],
        categories=CATEGORIES,
        errors=[
            HuntError(
                line_index=1 + 2 * i, related_lines=[10] if i == 0 else [], category=CATEGORIES[i % 4],
                explanation_options=["سبب صحيح", "سبب خاطئ 1", "سبب خاطئ 2"], correct_explanation=0,
                fix_options=["إصلاح صحيح", "إصلاح خاطئ 1", "إصلاح خاطئ 2"], correct_fix=0,
                hint_1="راجع الأعمدة", hint_2="انتبه للتواريخ",
            )
            for i in range(count)
        ],
    )


class GameAI(FakeAI):
    def __call__(self, prompt, output_model, *, task, max_tokens=32000, **kwargs):
        if output_model in (HuntFirstLevelOutput, HuntNextLevelOutput):
            self.calls.append((task, prompt))
            count = int(re.search(r"Number of mistakes: exactly (\d+)", prompt).group(1))
            if output_model is HuntFirstLevelOutput:
                mission = HuntMission(title="تقرير قبل التاسعة", story="قصة", goal="هدف", win_condition="اصطد كل الأخطاء")
                return HuntFirstLevelOutput(mission=mission, level=fake_level(count))
            return HuntNextLevelOutput(level=fake_level(count))
        return super().__call__(prompt, output_model, task=task, max_tokens=max_tokens, **kwargs)


@pytest.fixture
def ai(monkeypatch):
    fake = GameAI()
    monkeypatch.setattr(question_generator, "generate_structured", fake)
    return fake


@pytest.fixture
def c():
    with TestClient(app) as client:
        yield client


def _completed_assessment(c) -> str:
    aid = _start(c)
    for phase in ("skill", "knowledge"):
        state = c.post(f"/api/assessments/{aid}/{phase}/start").json()
        for _ in range(10):
            state = _answer(c, aid, phase, state["question"], correct=False).json()
    assert state["status"] == "completed"
    return aid


def _key(activity_id: str) -> dict:
    with SessionLocal() as db:
        a = db.query(LearningActivity).filter_by(activity_id=activity_id).one()
        return {e["line_index"]: e for e in a.levels[-1]["errors"]}


def _hunt_everything(c, act_id):
    for line, e in _key(act_id).items():
        if e["found"]:
            continue
        res = c.post(f"/api/activities/{act_id}/mark", json={"line_index": line, "category": e["category"]}).json()
        assert res["outcome"]["result"] == "found" and res["outcome"]["category_ok"]
        res = c.post(f"/api/activities/{act_id}/justify", json={
            "line_index": line, "explanation": e["correct_explanation"], "fix": e["correct_fix"]}).json()
        assert res["outcome"]["explanation_ok"] and res["outcome"]["fix_ok"]


def test_full_gap_hunter_play_through(c, ai):
    aid = _completed_assessment(c)
    report = c.get(f"/api/assessments/{aid}/report").json()
    step = report["learning_journey"][0]
    assert step["activity"]["activity_type"] in {"gap_hunter", "escape_room", "work_challenge", "shadow", "teach_others"}
    assert len(step["alternatives"]) == 4

    act = c.post(f"/api/assessments/{aid}/activities", json={"competency_id": step["competency_id"], "activity_type": "gap_hunter"}).json()
    act_id = act["activity_id"]
    assert act["mission"]["title"] and act["current_level"] == 1 and act["status"] == "playing"
    level = act["levels"][0]
    assert level["errors"] == [] and "hints" in level and level["hints"] == []  # answer key hidden
    assert "explanation_options" not in str(level)

    # Resuming returns the same activity, without another AI call
    again = c.post(f"/api/assessments/{aid}/activities", json={"competency_id": step["competency_id"], "activity_type": "gap_hunter"}).json()
    assert again["activity_id"] == act_id and len(ai.tasks("gap_hunter_level_1")) == 1

    # The evidence of the trainee's wrong answers reaches the generator
    assert '"trainee_chose"' in ai.tasks("gap_hunter_level_1")[0] or '"trainee_order"' in ai.tasks("gap_hunter_level_1")[0]

    # False alarm: costs points, XP never below zero, the game goes on
    res = c.post(f"/api/activities/{act_id}/mark", json={"line_index": 2, "category": CATEGORIES[0]}).json()
    assert res["outcome"]["result"] == "false_alarm" and res["activity"]["xp"] == 0
    assert res["outcome"]["why_correct"] == "السطر 2 سليم لأن…"  # the game teaches, not just marks wrong
    assert c.post(f"/api/activities/{act_id}/mark", json={"line_index": 2, "category": CATEGORIES[0]}).status_code == 409
    assert c.post(f"/api/activities/{act_id}/mark", json={"line_index": 0, "category": CATEGORIES[0]}).status_code == 422  # header

    # A related line (e.g. the original of a duplicate) counts as finding the same mistake
    key = _key(act_id)
    first = min(key)
    res = c.post(f"/api/activities/{act_id}/mark", json={"line_index": 10, "category": key[first]["category"]}).json()
    assert res["outcome"]["result"] == "found" and res["outcome"]["line_index"] == first
    c.post(f"/api/activities/{act_id}/justify", json={"line_index": 10, "explanation": key[first]["correct_explanation"], "fix": key[first]["correct_fix"]})

    # Hint costs XP; level 1 found perfectly except the hint
    hint = c.post(f"/api/activities/{act_id}/hint").json()
    assert hint["outcome"]["hint"] == "راجع الأعمدة"
    _hunt_everything(c, act_id)
    act = c.post(f"/api/activities/{act_id}/finish-level").json()
    assert act["current_level"] == 2 and len(act["levels"]) == 2 and act["levels"][0]["finished"]
    assert act["levels"][1]["difficulty"] >= act["levels"][0]["difficulty"]

    # Level 2: perfect without hints → "Hawk eye"
    _hunt_everything(c, act_id)
    act = c.post(f"/api/activities/{act_id}/finish-level").json()
    assert "hawk_eye" in {b["id"] for b in act["badges"]}

    # Level 3: give up early → mistakes are revealed with their answers, no punishment
    act = c.post(f"/api/activities/{act_id}/finish-level").json()
    revealed = act["levels"][2]["errors"]
    assert revealed and all(e["revealed"] and e["fix"] for e in revealed)
    assert act["levels"][3]["is_boss"] and act["levels"][3]["difficulty"] < act["levels"][2]["difficulty"] + 1

    # Boss: no hints; perfect run
    assert c.post(f"/api/activities/{act_id}/hint").status_code == 409
    _hunt_everything(c, act_id)
    act = c.post(f"/api/activities/{act_id}/finish-level").json()
    assert act["status"] == "completed"
    result = act["result"]
    assert result["boss_percent"] == 100 and result["score_after"] > result["score_before"]
    assert result["decision"] in {"passed", "partial"} and result["rank"]
    assert "boss_slayer" in {b["id"] for b in act["badges"]}

    progress = c.get(f"/api/assessments/{aid}/report").json()["learning_progress"][step["competency_id"]]
    assert progress["current"] == result["score_after"] and progress["activities"] == [act_id]


def test_activity_requires_completed_assessment(c, ai):
    aid = _completed_assessment(c)
    comp = c.get(f"/api/assessments/{aid}/report").json()["learning_journey"][0]["competency_id"]
    other = _start(c)
    assert c.post(f"/api/assessments/{other}/activities", json={"competency_id": comp, "activity_type": "gap_hunter"}).status_code == 409


def test_level_validator_requires_clean_structure():
    from backend.gap_hunter import validate_level

    level = fake_level(3)
    assert validate_level(level, 3) == []
    bad = level.model_copy(update={"errors": level.errors + [level.errors[0]]})
    problems = validate_level(bad, 3)
    assert any("exactly 3" in p for p in problems) and any("one error per line" in p for p in problems)
    overlap = level.model_copy(update={"errors": [level.errors[0].model_copy(update={"related_lines": [level.errors[1].line_index]})] + level.errors[1:]})
    assert any("one error per line" in p for p in validate_level(overlap, 3))
    header = level.model_copy(update={"errors": [level.errors[0].model_copy(update={"line_index": 0})] + level.errors[1:]})
    assert any("header" in p for p in validate_level(header, 3))
