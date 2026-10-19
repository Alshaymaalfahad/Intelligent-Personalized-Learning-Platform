from fastapi.testclient import TestClient

from backend import database
from backend.main import app

VALID = {
    "specialization": "Software Engineering",
    "interests": ["Software Testing", "Software Design and Architecture"],
    "additional_message": "I want to improve my ability to design reliable systems.",
}


def client() -> TestClient:
    return TestClient(app)


def test_create_profile_returns_structured_profile():
    with client() as c:
        res = c.post("/api/trainees", json=VALID)
    assert res.status_code == 201
    body = res.json()
    assert body["trainee_id"].startswith("TR-")
    assert body["specialization"] == "Software Engineering"
    assert body["interests"] == ["Software Testing", "Software Design and Architecture"]
    assert body["additional_message"] == VALID["additional_message"]
    assert body["profile_status"] == "completed"


def test_ids_are_unique():
    with client() as c:
        a = c.post("/api/trainees", json=VALID).json()["trainee_id"]
        b = c.post("/api/trainees", json=VALID).json()["trainee_id"]
    assert a != b


def test_profile_survives_restart():
    with client() as c:
        trainee_id = c.post("/api/trainees", json=VALID).json()["trainee_id"]
    database.engine.dispose()  # drop all connections, as a restart would
    with client() as c:
        res = c.get(f"/api/trainees/{trainee_id}")
    assert res.status_code == 200
    assert res.json()["interests"] == VALID["interests"]


def test_message_is_optional_and_blank_becomes_null():
    with client() as c:
        res = c.post("/api/trainees", json={**VALID, "additional_message": "   "})
    assert res.status_code == 201
    assert res.json()["additional_message"] is None


def test_catalog_names_are_normalized():
    with client() as c:
        res = c.post("/api/trainees", json={"specialization": "software engineering", "interests": ["software testing", "Software Testing", "اختبار البرمجيات"]})
    assert res.status_code == 201
    assert res.json()["specialization"] == "Software Engineering"
    assert res.json()["interests"] == ["Software Testing"]


def test_trainee_can_add_own_interests():
    with client() as c:
        res = c.post("/api/trainees", json={**VALID, "interests": ["Software Testing", "الحوسبة السحابية", "Microservices"]})
    assert res.status_code == 201
    assert res.json()["interests"] == ["Software Testing", "الحوسبة السحابية", "Microservices"]


def test_custom_specialization_accepts_free_interests():
    with client() as c:
        res = c.post("/api/trainees", json={"specialization": "Embedded Systems", "interests": ["Firmware"]})
    assert res.status_code == 201


def test_rejects_invalid_input():
    bad_payloads = [
        {"interests": ["Data Quality"]},  # missing specialization
        {**VALID, "specialization": " "},
        {**VALID, "interests": []},
        {**VALID, "interests": ["  "]},
        {**VALID, "interests": [f"area {i}" for i in range(7)]},  # more than 6
        {**VALID, "interests": ["x" * 61]},
        {**VALID, "additional_message": "x" * 501},
        {**VALID, "skill_level": "expert"},  # self-reported level is not accepted
    ]
    with client() as c:
        for payload in bad_payloads:
            assert c.post("/api/trainees", json=payload).status_code == 422, payload


def test_unknown_trainee_returns_404():
    with client() as c:
        assert c.get("/api/trainees/TR-9999").status_code == 404


def test_specializations_endpoint_and_frontend_served():
    with client() as c:
        specs = c.get("/api/specializations").json()
        assert any(s["name"] == "Information Systems" and s["interests"] for s in specs)
        assert c.get("/profile.html").status_code == 200
