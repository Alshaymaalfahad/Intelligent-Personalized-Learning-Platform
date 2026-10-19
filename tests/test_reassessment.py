"""Full cycle: assessment → learning journey (behavior tracked) → reassessment → new report."""

import pytest
from fastapi.testclient import TestClient

from backend import question_generator
from backend.database import SessionLocal
from backend.main import app
from backend.models import LearningEvent
from tests.test_assessment import _answer
from tests.test_gap_hunter import GameAI, _completed_assessment, _key


@pytest.fixture
def ai(monkeypatch):
    fake = GameAI()
    monkeypatch.setattr(question_generator, "generate_structured", fake)
    return fake


@pytest.fixture
def c():
    with TestClient(app) as client:
        yield client


def _play(c, aid, comp, *, explain_right=True) -> dict:
    act = c.post(f"/api/assessments/{aid}/activities", json={"competency_id": comp, "activity_type": "gap_hunter"}).json()
    act_id = act["activity_id"]
    while act["status"] == "playing":
        for line, e in _key(act_id).items():
            c.post(f"/api/activities/{act_id}/mark", json={"line_index": line, "category": e["category"]})
            explanation = e["correct_explanation"] if explain_right else (e["correct_explanation"] + 1) % 3
            c.post(f"/api/activities/{act_id}/justify", json={"line_index": line, "explanation": explanation, "fix": e["correct_fix"]})
        act = c.post(f"/api/activities/{act_id}/finish-level").json()
    return act


def test_behavior_is_recorded_per_attempt(c, ai):
    aid = _completed_assessment(c)
    comp = c.get(f"/api/assessments/{aid}/report").json()["learning_journey"][0]["competency_id"]
    act = c.post(f"/api/assessments/{aid}/activities", json={"competency_id": comp, "activity_type": "gap_hunter"}).json()
    act_id = act["activity_id"]
    c.post(f"/api/activities/{act_id}/mark", json={"line_index": 2, "category": "تكرار"})  # false alarm
    c.post(f"/api/activities/{act_id}/hint")
    line, e = next(iter(_key(act_id).items()))
    c.post(f"/api/activities/{act_id}/mark", json={"line_index": line, "category": e["category"]})
    c.post(f"/api/activities/{act_id}/justify", json={"line_index": line, "explanation": e["correct_explanation"], "fix": e["correct_fix"]})
    c.post(f"/api/activities/{act_id}/finish-level")
    with SessionLocal() as db:
        events = db.query(LearningEvent).order_by(LearningEvent.id).all()
        kinds = [ev.event_type for ev in events[-5:]]
        assert kinds == ["false_alarm", "hint", "mark_found", "justify", "finish_level"]
        assert [ev.attempt for ev in events[-5:]] == [1, 2, 3, 4, 5]
        assert events[-3].hints_so_far == 1 and events[-3].error_category == e["category"]
        assert all(ev.seconds_since_previous is not None for ev in events[-5:])
        assert events[-1].system_decision.startswith("next_level")


def test_full_cycle_with_reassessment(c, ai):
    aid = _completed_assessment(c)
    report = c.get(f"/api/assessments/{aid}/report").json()
    steps = report["learning_journey"]
    assert report["reassessment"]["eligible"] is False
    assert c.post(f"/api/assessments/{aid}/reassessment").status_code == 409

    # Baseline 0% needs two rounds to pass; the first step is played with weak justifications.
    first = steps[0]["competency_id"]
    for step in steps:
        for _ in range(2):
            act = _play(c, aid, step["competency_id"], explain_right=step["competency_id"] != first)
        assert act["result"]["decision"] == "passed"
        if step["competency_id"] == first:
            assert "weak_justification" in {sig["id"] for sig in act["result"]["behavior"]}

    info = c.get(f"/api/assessments/{aid}/report").json()["reassessment"]
    assert info["eligible"] and info["done_steps"] == len(steps)

    state = c.post(f"/api/assessments/{aid}/reassessment").json()
    rid = state["assessment_id"]
    assert state["kind"] == "reassessment" and rid != aid
    assert c.post(f"/api/assessments/{aid}/reassessment").json()["assessment_id"] == rid  # idempotent

    skill_steps = [s for s in steps if s["dimension"] == "skill"]
    knowledge_steps = [s for s in steps if s["dimension"] == "knowledge"]
    for phase, expected in (("skill", skill_steps), ("knowledge", knowledge_steps)):
        if not expected:
            continue
        state = c.post(f"/api/assessments/{rid}/{phase}/start").json()
        assert state["total"] == 2 * len(expected)
        while state["status"].endswith("_question"):
            state = _answer(c, rid, phase, state["question"], correct=True).json()

    assert state["status"] == "completed"
    prompts = ai.tasks("skill_question") + ai.tasks("knowledge_question")
    assert any("This is a REASSESSMENT" in p for p in prompts)
    assert any("right action for the wrong reason" in p for p in prompts)  # steered by weak justification

    new = c.get(f"/api/assessments/{rid}/report").json()
    assert new["kind"] == "reassessment" and new["parent_assessment_id"] == aid
    assert {row["competency_id"] for row in new["comparison"]} == {s["competency_id"] for s in steps}
    assert all(row["decision"] == "closed" and row["after"] > row["before"] for row in new["comparison"])

    # A new gap appeared: detects mistakes but justifies weakly → next journey step
    assert len(new["new_gaps"]) == 1 and new["new_gaps"][0]["competency_id"].startswith(first)
    assert [s["competency_id"] for s in new["learning_journey"]] == [new["new_gaps"][0]["competency_id"]]
    assert new["learning_journey"][0]["activity"]["activity_type"] in {"teach_others", "shadow"}

    # The new gap can be trained right away (Gap Hunter as an alternative)
    gap_id = new["new_gaps"][0]["competency_id"]
    res = c.post(f"/api/assessments/{rid}/activities", json={"competency_id": gap_id, "activity_type": "gap_hunter"})
    assert res.status_code == 201
