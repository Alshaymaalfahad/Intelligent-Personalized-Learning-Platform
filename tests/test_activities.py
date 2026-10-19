"""Briefing (lesson) + the four activities on activity_core, with a fake AI."""

import re

import pytest
from fastapi.testclient import TestClient

from backend import question_generator
from backend.activity_schemas import (
    CheckQuestion, EscapeDoor, EscapeFirstOutput, EscapeNextOutput, LessonContent, LessonSection, Mission,
    SaudAnswer, SaudQuizOutput, ShadowFirstOutput, ShadowLevel, ShadowMission, ShadowNextOutput, ShadowPause,
    ShadowStep, SolvedStep, TeachFirstOutput, TeachLevel, TeachNextOutput, TeachQuizQuestion, TeachTurn,
    WorkCriterion, WorkFirstOutput, WorkMission, WorkNextOutput, WorkReview, WorkTask, CriterionReview,
)
from backend.database import SessionLocal
from backend.models import LearningActivity, LearningEvent
from tests.test_gap_hunter import GameAI, _completed_assessment

MISSION = dict(title="مهمة", story="قصة قصيرة", goal="هدف", win_condition="شرط الفوز")


def door():
    return EscapeDoor(
        mentor_message="هيا", door_title="باب", scenario="موقف عمل قصير", artifact_kind="none", artifact_lines=[],
        challenge_type="choice", question="ما القرار؟", options=["صحيح", "خطأ 1", "خطأ 2", "خطأ 3"], correct_options=[0],
        option_consequences=["تقدّم العمل", "نتيجة سيئة 1", "نتيجة سيئة 2", "نتيجة سيئة 3"],
        justification_question="لماذا؟", justification_options=["سبب صحيح", "سبب خاطئ 1", "سبب خاطئ 2"],
        correct_justification=0, clue_sheet="ورقة دليل", hints=["تلميح 1", "تلميح 2"],
    )


def work_task():
    return WorkTask(
        mentor_message="هيا", sender_name="أ. سارة", sender_role="مديرة", subject="طلب", message="نحتاج تحليلًا",
        input_title="بيانات", input_lines=["a | b", "1 | 2"], deliverable_instructions="اكتب ردًا",
        acceptance_criteria=[WorkCriterion(criterion="معيار 1", points=1), WorkCriterion(criterion="معيار 2", points=2), WorkCriterion(criterion="معيار 3", points=1)],
        hints=["تلميح 1", "تلميح 2"], model_answer="عناصر الإجابة القوية",
    )


def shadow_level():
    return ShadowLevel(
        mentor_message="هيا", task_title="مهمة", situation="موقف", artifact_lines=[],
        expert_steps=[ShadowStep(step=f"خطوة {i}", why=f"لأن {i}", golden_practice=f"قاعدة {i}") for i in range(6)],
        pauses=[ShadowPause(step_index=i, distractors=[f"بديل {i}أ", f"بديل {i}ب"], hint="تلميح") for i in (1, 3, 5)],
        distractor_steps=["فخ 1", "فخ 2", "فخ 3"], hints=["تلميح 1", "تلميح 2"],
    )


def teach_level(boss: bool):
    return TeachLevel(
        mentor_message="هيا", concept="مفهوم", misconception="" if boss else "فكرة خاطئة", saud_opening="مرحبا، أظن أن…",
        key_points=["نقطة 1", "نقطة 2", "نقطة 3"], hints=["تلميح 1", "تلميح 2"],
        quiz=[TeachQuizQuestion(question=f"سؤال {i}", options=["أ", "ب", "ج", "د"], correct=0) for i in range(3)] if boss else [],
    )


def lesson(prompt: str) -> LessonContent:
    depth = re.search(r"# Depth of the explanation: (\w+)", prompt).group(1)
    n = {"compound": 3, "application": 1, "shallow": 2, "mastery": 1}[depth]
    return LessonContent(
        why_title="ليش مهم", why_story="تقرير طلع غلط", why_impact="خسارة يوم عمل", explanation_title="الشرح",
        sections=[LessonSection(emoji="📌", heading=f"قسم {i}", body="شرح", reveal_question="برأيك؟") for i in range(n)],
        takeaways=["1", "2", "3"], example_problem="مثال", example_lines=[],
        example_steps=[SolvedStep(step="خطوة", explanation="لأن"), SolvedStep(step="خطوة 2", explanation="لأن")],
        final_step_question="ما الخطوة الأخيرة؟", final_step_options=["صح", "خطأ أ", "خطأ ب"], final_step_correct=0,
        final_step_explanation="لأن…", check=[CheckQuestion(question="سؤال", options=["صح", "خطأ أ", "خطأ ب"], correct=0, explanation="لأن")],
    )


class AllAI(GameAI):
    def __call__(self, prompt, output_model, *, task, max_tokens=32000, **kwargs):
        boss = "This is the BOSS level" in prompt
        made = {
            EscapeFirstOutput: lambda: EscapeFirstOutput(mission=Mission(**MISSION), door=door()),
            EscapeNextOutput: lambda: EscapeNextOutput(door=door()),
            WorkFirstOutput: lambda: WorkFirstOutput(mission=WorkMission(**MISSION, job_title="محلل نظم"), task=work_task()),
            WorkNextOutput: lambda: WorkNextOutput(task=work_task()),
            WorkReview: lambda: WorkReview(criteria=[CriterionReview(criterion=f"معيار {i}", status="met" if "كامل" in prompt.split("<deliverable>")[-1] else "partial", comment="تعليق") for i in range(3)], manager_feedback="عمل جيد", confidence=0.9),
            ShadowFirstOutput: lambda: ShadowFirstOutput(mission=ShadowMission(**MISSION, expert_name="م. خالد"), level=shadow_level()),
            ShadowNextOutput: lambda: ShadowNextOutput(level=shadow_level()),
            TeachFirstOutput: lambda: TeachFirstOutput(mission=Mission(**MISSION), level=teach_level(False)),
            TeachNextOutput: lambda: TeachNextOutput(level=teach_level(boss)),
            TeachTurn: lambda: TeachTurn(covered_points=[0, 1, 2], accurate=True, has_example=True, clarity="clear", understanding=95, saud_reply="فهمت!"),
            SaudQuizOutput: lambda: SaudQuizOutput(answers=[SaudAnswer(question_index=i, chosen_option=0, reasoning="لأنك قلت") for i in range(3)], saud_message="شكرًا"),
            LessonContent: lambda: lesson(prompt),
        }
        if output_model in made:
            self.calls.append((task, prompt))
            return made[output_model]()
        return super().__call__(prompt, output_model, task=task, max_tokens=max_tokens, **kwargs)


@pytest.fixture
def ai(monkeypatch):
    fake = AllAI()
    monkeypatch.setattr(question_generator, "generate_structured", fake)
    return fake


@pytest.fixture
def c():
    with TestClient(app_()) as client:
        yield client


def app_():
    from backend.main import app
    return app


def _start(c, aid, comp, kind):
    res = c.post(f"/api/assessments/{aid}/activities", json={"competency_id": comp, "activity_type": kind})
    assert res.status_code == 201, res.text
    return res.json()


def _act(c, act_id, action, payload):
    res = c.post(f"/api/activities/{act_id}/action", json={"action": action, "payload": payload})
    assert res.status_code == 200, res.text
    return res.json()


def _key(act_id):
    with SessionLocal() as db:
        return db.query(LearningActivity).filter_by(activity_id=act_id).one().levels[-1]


def _finish(c, act_id):
    res = c.post(f"/api/activities/{act_id}/finish-level")
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def journey(c, ai):
    aid = _completed_assessment(c)
    steps = c.get(f"/api/assessments/{aid}/report").json()["learning_journey"]
    return aid, steps


def test_lesson_before_activity(c, ai, journey):
    aid, steps = journey
    comp = steps[0]["competency_id"]
    info = c.get(f"/api/assessments/{aid}/lessons/{comp}").json()
    assert info["depth"] in {"compound", "application", "shallow", "mastery"} and info["lesson"] is None
    assert {s["id"] for s in info["styles"]} == {"brief", "story", "visual", "interactive"}

    lesson = c.post(f"/api/assessments/{aid}/lessons/{comp}", json={"style": "visual"}).json()
    assert lesson["style"] == "visual" and lesson["why"]["story"] and len(lesson["explanation"]["takeaways"]) == 3
    assert "correct" not in str(lesson["check"]) and "final_step_correct" not in str(lesson)  # answers not leaked
    assert '"trainee_chose"' in ai.tasks("lesson")[0] or '"trainee_order"' in ai.tasks("lesson")[0]  # targets the misconception

    lid = lesson["lesson_id"]
    r = c.post(f"/api/lessons/{lid}/final-step", json={"choice": 2}).json()
    assert r["explanation"] and isinstance(r["correct"], bool)
    r = c.post(f"/api/lessons/{lid}/check", json={"index": 0, "choice": 1}).json()
    assert r["explanation"]
    assert c.post(f"/api/lessons/{lid}/complete").json()["completed"] is True
    assert c.get(f"/api/assessments/{aid}/report").json()["lessons"][comp] == {"completed": True, "style": "visual"}

    # «📖 راجع الشرح» from inside an activity: free, recorded as behavior
    act = _start(c, aid, comp, "escape_room")
    xp = act["xp"]
    assert c.post(f"/api/activities/{act['activity_id']}/review-lesson").json()["lesson_id"] == lid
    assert c.get(f"/api/activities/{act['activity_id']}").json()["xp"] == xp
    with SessionLocal() as db:
        assert db.query(LearningEvent).filter_by(event_type="review_lesson").count() == 1

    # After an activity, the style that worked is suggested
    while act["status"] == "playing":
        lv = _key(act["activity_id"])
        _act(c, act["activity_id"], "answer", {"selected": lv["content"]["correct"]})
        _act(c, act["activity_id"], "justify", {"choice": lv["content"]["correct_justification"]})
        act = _finish(c, act["activity_id"])
    assert "lesson_reviews" in {s["id"] for s in act["result"]["behavior"]}
    assert c.get(f"/api/assessments/{aid}/lessons/{steps[1]['competency_id']}").json()["suggested_style"] == "visual"


def test_escape_room(c, ai, journey):
    aid, steps = journey
    act = _start(c, aid, steps[0]["competency_id"], "escape_room")
    act_id = act["activity_id"]
    view = act["levels"][0]
    assert view["kind"] == "door" and "correct" not in view and "clue_sheet" not in view

    lv = _key(act_id)
    wrong = [i for i in range(4) if i not in lv["content"]["correct"]][0]
    out = _act(c, act_id, "answer", {"selected": [wrong]})
    assert out["outcome"]["result"] == "retry" and out["outcome"]["consequence"]
    assert out["activity"]["levels"][0]["clue_sheet"] == "ورقة دليل"  # the mentor explains, not just «wrong»
    out = _act(c, act_id, "answer", {"selected": lv["content"]["correct"]})
    assert out["outcome"]["result"] == "solved" and out["outcome"]["xp_change"] == 15
    out = _act(c, act_id, "justify", {"choice": lv["content"]["correct_justification"]})
    assert out["outcome"]["justification_ok"] and out["outcome"]["digit"] == lv["state"]["digit"]
    act = _finish(c, act_id)
    assert act["current_level"] == 2 and "digit" in act["levels"][0]

    prompt = ai.tasks("escape_room_level_2")[0]
    assert "consequence_of_decision" in prompt  # the decision shapes the next door

    while act["status"] == "playing":
        lv = _key(act_id)
        _act(c, act_id, "answer", {"selected": lv["content"]["correct"]})
        _act(c, act_id, "justify", {"choice": lv["content"]["correct_justification"]})
        act = _finish(c, act_id)
    assert act["result"]["decision"] in {"passed", "partial"} and act["result"]["rank"]


def test_work_challenge(c, ai, journey):
    aid, steps = journey
    act = _start(c, aid, steps[0]["competency_id"], "work_challenge")
    act_id = act["activity_id"]
    lv = act["levels"][0]
    assert lv["kind"] == "work" and "model_answer" not in lv and len(lv["criteria"]) == 3

    out = _act(c, act_id, "submit", {"text": "تسليم أولي فيه بعض العناصر فقط"})
    first = out["outcome"]["submission"]
    assert first["percent"] == 50 and first["stars"] == 3 and first["feedback"]
    out = _act(c, act_id, "submit", {"text": "تسليم كامل يغطي كل المعايير بدقة"})
    assert out["outcome"]["submission"]["stars"] == 5 and out["activity"]["levels"][0]["best_percent"] == 100
    assert "<deliverable>" in ai.tasks("work_review")[0]  # trainee text wrapped as untrusted

    act = _finish(c, act_id)
    assert act["levels"][0]["model_answer"] and act["levels"][1]["surprise"] is True
    assert "client_star" in {b["id"] for b in act["badges"]}
    while act["status"] == "playing":
        _act(c, act_id, "submit", {"text": "تسليم كامل يغطي كل المعايير بدقة"})
        act = _finish(c, act_id)
    assert act["result"]["rank"] in {"متدرب", "محلل نظم", "محلل نظم أول"}


def test_shadow(c, ai, journey):
    aid, steps = journey
    act = _start(c, aid, steps[0]["competency_id"], "shadow")
    act_id = act["activity_id"]
    lv = act["levels"][0]
    assert lv["mode"] == "watch" and len(lv["visible_steps"]) == 1 and lv["current_pause"]["number"] == 1

    for _ in range(3):
        key = _key(act_id)
        pause = key["content"]["pauses"][key["state"]["pause"]]
        out = _act(c, act_id, "predict", {"choice": pause["correct"]})
        assert out["outcome"]["card"]
    assert len(out["activity"]["levels"][0]["cards"]) == 3 and out["activity"]["levels"][0]["done"]
    act = _finish(c, act_id)
    assert "golden_collector" in {b["id"] for b in act["badges"]}

    lv = act["levels"][1]
    assert lv["mode"] == "do" and len(lv["pool"]) == 9
    key = _key(act_id)
    expert_order = sorted((p["expert_index"], i) for i, p in enumerate(key["content"]["pool"]) if p["expert_index"] is not None)
    out = _act(c, act_id, "submit_steps", {"order": [i for _, i in expert_order]})
    assert out["outcome"]["match"] == 100
    act = _finish(c, act_id)
    pool = _key(act_id)["content"]["pool"]  # each level shuffles its own cards
    experts = [i for _, i in sorted((p["expert_index"], i) for i, p in enumerate(pool) if p["expert_index"] is not None)]
    trap = next(i for i, p in enumerate(pool) if p["expert_index"] is None)
    out = _act(c, act_id, "submit_steps", {"order": experts[:3][::-1] + [trap]})
    comp = out["activity"]["levels"][2]["comparison"]
    assert 0 < out["outcome"]["match"] < 100 and any(e["missed"] for e in comp["expert"])
    assert any(t["status"] == "extra" for t in comp["trainee"])
    act = _finish(c, act_id)
    assert act["status"] == "completed"


def test_teach_others(c, ai, journey):
    aid, steps = journey
    act = _start(c, aid, steps[0]["competency_id"], "teach_others")
    act_id = act["activity_id"]
    lv = act["levels"][0]
    assert lv["kind"] == "teach" and lv["messages"][0]["from"] == "saud" and "key_points" not in lv

    out = _act(c, act_id, "explain", {"text": "يا سعود، الفكرة إن… مثال: …"})
    assert out["outcome"]["meter"] == 40  # capped: at most +40 per message
    out = _act(c, act_id, "explain", {"text": "ونقطة ثانية مهمة: …"})
    assert out["outcome"]["meter"] == 80 and out["activity"]["levels"][0]["messages"][-1]["text"] == "فهمت!"
    assert "<" not in ai.tasks("teach_turn")[0].split("# Conversation so far")[1].split("# Your job")[0].replace("‹", "")
    act = _finish(c, act_id)
    while not act["levels"][-1]["quiz_size"]:
        _act(c, act_id, "explain", {"text": "شرح واضح مع مثال عملي"})
        act = _finish(c, act_id)

    boss = act["levels"][-1]
    assert boss["is_boss"] and boss["quiz_result"] is None
    out = _act(c, act_id, "final_lesson", {"text": "ملخص أخير لسعود قبل الاختبار"})
    result = out["activity"]["levels"][-1]["quiz_result"]
    key = _key(act_id)["content"]["quiz"]
    assert [r["saud_correct"] for r in result] == [q["correct"] == 0 for q in key]  # graded by the server
    assert out["outcome"]["saud_passed"] == (sum(q["correct"] == 0 for q in key) >= 2)
    act = _finish(c, act_id)
    assert act["status"] == "completed" and act["result"]["rank"]
