"""Skills page → journey (no placement test): own-ID sign-up, ordering, the 5-skill limit,
the selection lock until the journey is done, and lessons/activities on the journey (fake AI)."""

import itertools

from tests.test_activities import _act, _finish, _key, _start, ai, c  # noqa: F401 (fixtures)

_ids = itertools.count(1)


def _new_id():
    return f"tester{next(_ids)}x"


def _create(c, picks, lang="ar", trainee_id=None, new=True, headers=None):
    res = c.post("/api/journeys", json={"trainee_id": trainee_id or _new_id(), "new_trainee": new, "language": lang,
                                        "selections": picks}, headers=headers or {})
    assert res.status_code == 201, res.text
    return res.json()


def _play_through(c, jid, comp):
    act = _start(c, jid, comp, "escape_room")
    while act["status"] == "playing":
        lv = _key(act["activity_id"])
        _act(c, act["activity_id"], "answer", {"selected": lv["content"]["correct"]})
        _act(c, act["activity_id"], "justify", {"choice": lv["content"]["correct_justification"]})
        act = _finish(c, act["activity_id"])
    return act


def test_skills_catalog(c):
    cat = c.get("/api/skills", headers={"X-Lang": "ar"}).json()
    assert len(cat["stages"]) == 5 and len(cat["axes"]) == 11 and cat["max_active"] == 5
    ids = {s["id"] for s in cat["skills"]}
    for b in cat["bundles"]:
        assert set(b["skills"]) <= ids
    for skill, pres in cat["prerequisites"].items():
        assert skill in ids and set(pres) <= ids
    assert all(s["name"] and s["can_do"] and s["learn"] and s["example"] and s["minutes"] > 0 for s in cat["skills"])
    vibe = next(a for a in cat["axes"] if a["id"] == "A5")
    assert vibe["stage"] == "build" and sum(s["axis"] == "A5" for s in cat["skills"]) == 6
    assert c.get("/api/skills", headers={"X-Lang": "en"}).json()["axes"][0]["name"] == "Research & competitor analysis"


def test_signup_with_own_id(c):
    j = _create(c, [{"skill_id": "L1-1"}], trainee_id=" Noura2026 ")
    assert j["trainee_id"] == "NOURA2026" and j["journey_id"].startswith("JR-") and len(j["journey_id"]) == 13
    assert c.get("/api/trainees/noura2026/progress").json()["journey_id"] == j["journey_id"]  # case-insensitive

    taken = c.post("/api/journeys", json={"trainee_id": "NOURA2026", "new_trainee": True, "selections": [{"skill_id": "L1-2"}]},
                   headers={"X-Lang": "en"})
    assert taken.status_code == 409 and taken.json()["detail"] == "This ID is taken — choose another one."
    for bad in ["abc12", "onlyletters", "12345678", "has space1", "سارة2026"]:
        res = c.post("/api/journeys", json={"trainee_id": bad, "new_trainee": True, "selections": [{"skill_id": "L1-1"}]})
        assert res.status_code == 422, bad
    missing = c.post("/api/journeys", json={"trainee_id": "ghost123", "new_trainee": False, "selections": [{"skill_id": "L1-1"}]})
    assert missing.status_code == 404


def test_journey_order_and_limit(c):
    picks = ["L11-1", "L7-3", "L5-1", "L9-1", "L6-3", "L7-2", "L1-1"]
    j = _create(c, [{"skill_id": s} for s in picks])
    order = [s["skill_id"] for s in j["stations"]]
    # lab order, prerequisite first (prompts before Vibe Coding), at most 5 active
    assert order == ["L1-1", "L9-1", "L5-1", "L6-3", "L7-2"]
    assert [s["skill_id"] for s in j["later"]] == ["L7-3", "L11-1"]
    assert [s["state"] for s in j["stations"]] == ["current"] + ["upcoming"] * 4
    assert j["total_minutes"] == sum(s["minutes"] for s in j["stations"]) and j["complete"] is False

    bad = c.post("/api/journeys", json={"trainee_id": _new_id(), "new_trainee": True, "selections": [{"skill_id": "NOPE"}]},
                 headers={"X-Lang": "en"})
    assert bad.status_code == 422 and bad.json()["detail"] == "Unknown skill."
    only_later = c.post("/api/journeys", json={"trainee_id": _new_id(), "new_trainee": True, "selections": [{"skill_id": "L1-1", "later": True}]})
    assert only_later.status_code == 422


def test_level_sets_lesson_depth(c):
    j = _create(c, [{"skill_id": "L1-1", "level": "new"}, {"skill_id": "L1-2", "level": "deep"}, {"skill_id": "L1-3"}])
    jid = j["journey_id"]
    new = c.get(f"/api/assessments/{jid}/lessons/L1-1").json()
    deep = c.get(f"/api/assessments/{jid}/lessons/L1-2").json()
    default = c.get(f"/api/assessments/{jid}/lessons/L1-3").json()
    assert new["depth"] == "compound" and not new["can_skip"]
    assert deep["depth"] == "mastery" and deep["can_skip"]
    assert default["depth"] == "application"


def test_selection_locked_until_journey_done(c, ai):
    tid = _new_id()
    j = _create(c, [{"skill_id": "L5-3", "level": "new"}, {"skill_id": "L1-1"}, {"skill_id": "L1-2", "later": True}], trainee_id=tid)
    jid = j["journey_id"]
    assert c.post("/api/journeys", json={"trainee_id": tid, "selections": [{"skill_id": "L2-1"}]}).status_code == 409
    assert c.put(f"/api/journeys/{jid}", json={"selections": [{"skill_id": "L2-1"}]}).status_code == 405  # no editing
    # a «later» skill is not a station
    res = c.post(f"/api/assessments/{jid}/activities", json={"competency_id": "L1-2", "activity_type": "escape_room"})
    assert res.status_code == 404

    _play_through(c, jid, "L1-1")
    assert c.post("/api/journeys", json={"trainee_id": tid, "selections": [{"skill_id": "L2-1"}]}).status_code == 409
    _play_through(c, jid, "L5-3")
    view = c.get(f"/api/journeys/{jid}").json()
    assert view["complete"] and view["done"] == 2
    progress = c.get(f"/api/trainees/{tid}/progress").json()
    assert progress["journey_complete"] is True

    # every station done: the next round opens
    nxt = _create(c, [{"skill_id": "L1-2"}, {"skill_id": "L2-1"}], trainee_id=tid, new=False)
    assert nxt["journey_id"] != jid and [s["state"] for s in nxt["stations"]] == ["current", "upcoming"]
    assert c.get(f"/api/trainees/{tid}/progress").json()["journey_id"] == nxt["journey_id"]


def test_lesson_and_activity_on_journey(c, ai):
    j = _create(c, [{"skill_id": "L5-3", "level": "new"}, {"skill_id": "L1-1"}])
    jid = j["journey_id"]
    report = c.get(f"/api/assessments/{jid}/report", headers={"X-Lang": "en"}).json()
    assert report["trainee_id"] == j["trainee_id"] and report["learning_journey"][0]["name"] == "Quickly finding similar solutions"

    lesson = c.post(f"/api/assessments/{jid}/lessons/L5-3", json={"style": "brief"}).json()
    assert lesson["lesson_id"].startswith("LS-") and len(lesson["lesson_id"]) == 13
    prompt = ai.tasks("lesson")[0]
    assert "مراجعة الكود المولَّد" in prompt and "AI solutions lab" in prompt

    act = _start(c, jid, "L5-3", "escape_room")
    assert act["activity_id"].startswith("LA-") and len(act["activity_id"]) == 13
    started = c.get(f"/api/journeys/{jid}").json()["stations"]
    assert [s["skill_id"] for s in started] == ["L1-1", "L5-3"] and started[1]["started"]
    assert c.post(f"/api/assessments/{jid}/reassessment").status_code == 409


def test_content_follows_language_on_screen(c, ai):
    """Signed up in Arabic, now browsing in English: new AI content is written in English."""
    j = _create(c, [{"skill_id": "L9-1"}], lang="ar")
    jid = j["journey_id"]
    c.post(f"/api/assessments/{jid}/lessons/L9-1", json={"style": "brief"}, headers={"X-Lang": "en"})
    prompt = ai.tasks("lesson")[-1]
    assert "Writing structured prompts" in prompt and "كتابة أوامر منظمة" not in prompt
    assert "English" in prompt


def test_progress_is_measured_not_self_rated(c, ai):
    """A self-rated level is never shown as progress: 0 until the final challenge, then its real result."""
    j = _create(c, [{"skill_id": "L1-1", "level": "deep"}])
    jid = j["journey_id"]
    assert j["stations"][0]["score"] == 0
    step = c.get(f"/api/assessments/{jid}/report").json()["learning_journey"][0]
    assert step["baseline_score"] == 0 and step["self_rated"] is True

    act = _play_through(c, jid, "L1-1")
    r = act["result"]
    assert r["score_before"] == 0 and r["score_after"] == r["boss_percent"]  # all correct → the real boss result
    assert c.get(f"/api/journeys/{jid}").json()["stations"][0]["score"] == r["boss_percent"]
