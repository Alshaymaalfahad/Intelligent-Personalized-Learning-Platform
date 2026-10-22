"""Turns graded answers into per-competency results and the gap report.

Fully deterministic (no AI): the same answers always give the same report.
Skills and knowledge are scored and reported separately — never averaged together.
"""

from .adaptive_selector import BLOOM_LEVELS, passed
from .learning_activities import activity_card, choose_activities

TARGET_SCORE = 70  # required level (%) for every competency in this prototype
STRENGTH_SCORE = 80
LIKELY_GAP_SCORE = 50
MIN_QUESTIONS_FOR_EVIDENCE = 2
LOW_CONFIDENCE = 0.6

IMPORTANCE_WEIGHT = {1: 1.0, 2: 1.5, 3: 2.0}
LINKED_GAP_BONUS = 10  # a skill gap backed by a knowledge gap (or vice versa) is more urgent

# Status codes (the frontend translates them): strength | adequate | potential_gap | likely_gap | insufficient_evidence
GAP_STATUSES = {"potential_gap", "likely_gap"}


def _classify(score: float, sufficient: bool) -> str:
    if not sufficient:
        return "insufficient_evidence"
    if score >= STRENGTH_SCORE:
        return "strength"
    if score >= TARGET_SCORE:
        return "adequate"
    if score >= LIKELY_GAP_SCORE:
        return "potential_gap"
    return "likely_gap"


def competency_results(competencies: list[dict], questions: list, dimension: str) -> list[dict]:
    """Score = Σ earned / Σ max × 100 over the questions linked to each competency."""
    results = []
    for comp in competencies:
        linked = [q for q in questions if q.competency_id == comp["competency_id"]]
        earned = sum(q.earned_score or 0 for q in linked)
        maximum = sum(q.max_score for q in linked)
        score = round(100 * earned / maximum, 1) if maximum else 0.0
        low_confidence = sum(1 for q in linked if (q.grading_confidence or 0) < LOW_CONFIDENCE)
        reliable = len(linked) - low_confidence
        sufficient = reliable >= MIN_QUESTIONS_FOR_EVIDENCE
        status = _classify(score, sufficient)
        results.append({
            "competency_id": comp["competency_id"],
            "name": comp["name"],
            "dimension": dimension,
            "importance": comp["importance"],
            "skill_kind": comp.get("skill_kind"),
            "related_skill_ids": comp.get("related_skill_ids", []),
            "score": score,
            "target_score": TARGET_SCORE,
            "earned_points": earned,
            "max_points": maximum,
            "question_count": len(linked),
            "question_types": sorted({q.question_type for q in linked}),
            "low_confidence_count": low_confidence,
            "evidence": [
                {
                    "question_id": q.question_id,
                    "question_type": q.question_type,
                    "difficulty": q.difficulty,
                    "bloom_level": q.bloom_level,
                    "result_percent": round(100 * (q.earned_score or 0) / q.max_score),
                }
                for q in linked
            ],
            "status": status,
        })
        if dimension == "knowledge":
            # Highest Bloom level the trainee answered correctly in this area.
            reached = [q.bloom_level for q in linked if passed(q)]
            top = max(reached, key=BLOOM_LEVELS.index) if reached else None
            results[-1]["bloom_reached"] = top
    return results


def _dimension_summary(results: list[dict]) -> dict:
    earned = sum(r["earned_points"] for r in results)
    maximum = sum(r["max_points"] for r in results)
    return {
        "score": round(100 * earned / maximum, 1) if maximum else 0.0,
        "competency_count": len(results),
        "gap_count": sum(1 for r in results if r["status"] in GAP_STATUSES),
    }


def _insights(skills: list[dict], knowledge: list[dict]) -> list[dict]:
    """Contrast knowledge with the skills it supports (e.g. knows the concept but can't apply it)."""
    by_skill = {s["competency_id"]: s for s in skills}
    insights = []
    for k in knowledge:
        for sid in k["related_skill_ids"]:
            s = by_skill.get(sid)
            if s is None:
                continue
            k_ok = k["score"] >= TARGET_SCORE
            s_ok = s["score"] >= TARGET_SCORE
            if k_ok and not s_ok:
                kind = "knows_not_applies"
            elif s_ok and not k_ok:
                kind = "applies_not_knows"
            elif not k_ok and not s_ok:
                kind = "both_weak"
            else:
                continue
            if all(i["skill_id"] != sid or i["type"] != kind for i in insights):  # one note per skill and kind
                insights.append({"type": kind, "skill_id": sid, "skill_name": s["name"],
                                 "knowledge_id": k["competency_id"], "knowledge_name": k["name"]})
    return insights


def _priorities(skills: list[dict], knowledge: list[dict]) -> list[dict]:
    weak_ids = {r["competency_id"] for r in skills + knowledge if r["score"] < TARGET_SCORE}
    linked_to_weak: set[str] = set()
    for k in knowledge:
        for sid in k["related_skill_ids"]:
            if k["competency_id"] in weak_ids and sid in weak_ids:
                linked_to_weak |= {k["competency_id"], sid}

    needs = []
    for r in skills + knowledge:
        gap = TARGET_SCORE - r["score"]
        if gap <= 0:
            continue
        evidence_weight = 1.0 if r["status"] != "insufficient_evidence" else 0.6
        priority = gap * IMPORTANCE_WEIGHT[r["importance"]] * evidence_weight
        reasons = [{"code": "gap_points", "value": round(gap)}]
        if r["importance"] == 3:
            reasons.append({"code": "core"})
        if r["competency_id"] in linked_to_weak:
            priority += LINKED_GAP_BONUS
            reasons.append({"code": "linked_knowledge" if r["dimension"] == "skill" else "linked_skill"})
        if r["status"] == "insufficient_evidence":
            reasons.append({"code": "limited_evidence"})
        needs.append({
            "competency_id": r["competency_id"],
            "name": r["name"],
            "dimension": r["dimension"],
            "score": r["score"],
            "target_score": TARGET_SCORE,
            "status": r["status"],
            "skill_kind": r.get("skill_kind"),
            "priority_score": round(priority, 1),
            "reasons": reasons,
        })
    needs.sort(key=lambda n: n["priority_score"], reverse=True)
    for rank, n in enumerate(needs, start=1):
        n["rank"] = rank
    return needs


# ---------------------------------------------------------------------------
# Learning journey: one gamified activity per gap (alternatives if the gap persists)
# ---------------------------------------------------------------------------

MAX_JOURNEY_STEPS = 5


def _journey(needs: list[dict], results: dict[str, dict]) -> list[dict]:
    steps = []
    for need in needs[:MAX_JOURNEY_STEPS]:
        r = results[need["competency_id"]]
        missed = [e["question_type"] for e in r["evidence"] if e["result_percent"] < 50]
        order = choose_activities(r, missed)
        steps.append({
            "step": len(steps) + 1,
            "competency_id": r["competency_id"],
            "name": r["name"],
            "dimension": r["dimension"],
            "skill_kind": r["skill_kind"] if r["dimension"] == "skill" else None,
            "baseline_score": r["score"],
            "activity": activity_card(order[0]),
            "alternatives": [activity_card(a) for a in order[1:]],
        })
    return steps


def _ref(r: dict) -> dict:
    return {k: r[k] for k in ("competency_id", "name", "dimension", "score", "status")}


def build_report(assessment, skill_results: list[dict], knowledge_results: list[dict]) -> dict:
    """Output designed to feed the future learning-journey phase directly."""
    all_results = skill_results + knowledge_results
    needs = _priorities(skill_results, knowledge_results)
    trainee = assessment.trainee
    return {
        "trainee_id": trainee.trainee_id,
        "assessment_id": assessment.assessment_id,
        "specialization": trainee.specialization,
        "interests": trainee.interests,
        "assessment_status": "completed",
        "target_score": TARGET_SCORE,
        "skill_summary": _dimension_summary(skill_results),
        "knowledge_summary": _dimension_summary(knowledge_results),
        "skill_results": skill_results,
        "knowledge_results": knowledge_results,
        "strengths": [_ref(r) for r in all_results if r["status"] == "strength"],
        "potential_gaps": [_ref(r) for r in all_results if r["status"] in GAP_STATUSES],
        "insufficient_evidence": [_ref(r) for r in all_results if r["status"] == "insufficient_evidence"],
        "insights": _insights(skill_results, knowledge_results),
        "prioritized_learning_needs": needs,
        "learning_journey": _journey(needs, {r["competency_id"]: r for r in all_results}),
        "adaptation_summary": assessment.adaptation_summary,
    }
