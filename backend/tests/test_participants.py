"""Studies, participant registration, ownership segregation and audit (US-06 to US-08, US-27, US-30).

Expected rows are read from the seeded database, so these tests keep working
if the seed data changes.
"""
import pytest
from sqlalchemy import text

from tests.conftest import owned_by, query


def ids(response) -> set[int]:
    assert response.status_code == 200, response.text
    return {p["participant_id"] for p in response.json()}


def any_study() -> tuple[int, str]:
    return query("SELECT study_id, study_code FROM studies WHERE active ORDER BY study_id LIMIT 1")[0]


def next_code(study_id: int) -> str:
    highest = query("SELECT COALESCE(MAX(substr(participant_code, 3)::int), 0) "
                    "FROM participants WHERE study_id = %s", (study_id,))[0][0]
    return f"P-{highest + 1:04d}"


def one_of(participant_ids: set[int]) -> int:
    assert participant_ids, "Seed needs participants for every staff member"
    return min(participant_ids)


# ---------- Studies ----------

def test_coordinator_creates_study_and_it_is_audited(client, coord1, db):
    response = client.post("/api/studies", headers=coord1, json={
        "study_code": "STD-TEST-99", "title": "Test Study For Audit", "study_type": "OBSERVATIONAL"})
    assert response.status_code == 201
    study_id = response.json()["study_id"]
    action = db.execute(text("SELECT action FROM audit_events WHERE entity_type='study' AND entity_id=:i"),
                        {"i": study_id}).scalar()
    assert action == "STUDY_CREATED"


def test_duplicate_study_code_returns_409(client, coord1):
    _, code = any_study()
    response = client.post("/api/studies", headers=coord1, json={
        "study_code": code, "title": "Duplicate code", "study_type": "REGISTRY"})
    assert response.status_code == 409


def test_invalid_study_code_returns_422(client, coord1):
    response = client.post("/api/studies", headers=coord1, json={
        "study_code": "sleep", "title": "Bad code study", "study_type": "REGISTRY"})
    assert response.status_code == 422


def test_both_roles_can_list_studies(client, coord1, rev1):
    total = query("SELECT COUNT(*) FROM studies")[0][0]
    assert len(client.get("/api/studies", headers=coord1).json()) == total
    assert len(client.get("/api/studies", headers=rev1).json()) == total


# ---------- Segregation: lists ----------

@pytest.mark.parametrize("who, index", [("coord", 0), ("coord", 1), ("rev", 0), ("rev", 1)])
def test_each_user_lists_only_their_own_participants(client, request, coordinators, reviewers, who, index):
    code = (coordinators if who == "coord" else reviewers)[index]
    headers = request.getfixturevalue(f"{who}{index + 1}")
    assert ids(client.get("/api/participants", headers=headers)) == owned_by(code)


def test_the_two_coordinators_never_share_participants(client, coord1, coord2):
    first = ids(client.get("/api/participants", headers=coord1))
    second = ids(client.get("/api/participants", headers=coord2))
    assert first and second and first.isdisjoint(second)


def test_the_two_reviewers_never_share_participants(client, rev1, rev2):
    first = ids(client.get("/api/participants", headers=rev1))
    second = ids(client.get("/api/participants", headers=rev2))
    assert first and second and first.isdisjoint(second)


def test_study_filter_keeps_the_ownership_limit(client, coord1, coordinators):
    study_id, _ = any_study()
    rows = client.get(f"/api/participants?study_id={study_id}", headers=coord1).json()
    assert all(r["study_id"] == study_id and r["coordinator_code"] == coordinators[0] for r in rows)


# ---------- Segregation: single records ----------

def test_coordinator_gets_404_for_another_coordinators_participant(client, coord1, coord2, coordinators):
    others = one_of(owned_by(coordinators[1]))
    assert client.get(f"/api/participants/{others}", headers=coord1).status_code == 404
    assert client.get(f"/api/participants/{others}", headers=coord2).status_code == 200


def test_reviewer_gets_404_for_a_participant_not_assigned_to_them(client, rev1, rev2, reviewers):
    others = one_of(owned_by(reviewers[1]))
    assert client.get(f"/api/participants/{others}", headers=rev1).status_code == 404
    assert client.get(f"/api/participants/{others}", headers=rev2).status_code == 200


def test_404_does_not_reveal_whether_the_record_exists(client, coord1, coordinators):
    other = client.get(f"/api/participants/{one_of(owned_by(coordinators[1]))}", headers=coord1)
    missing = client.get("/api/participants/999999", headers=coord1)
    assert other.status_code == missing.status_code == 404
    assert other.json().keys() == missing.json().keys()


def test_participant_detail_lists_visits_newest_first(client, coord1, coordinators):
    with_visits = query("SELECT p.participant_id FROM participants p JOIN visits v USING (participant_id) "
                        "WHERE p.coordinator_code = %s GROUP BY 1 HAVING COUNT(*) >= 2 LIMIT 1",
                        (coordinators[0],))
    if not with_visits:
        pytest.skip("Seed has no participant with two visits for this coordinator")
    body = client.get(f"/api/participants/{with_visits[0][0]}", headers=coord1).json()
    dates = [v["scheduled_for"] for v in body["visits"]]
    assert len(dates) >= 2 and dates == sorted(dates, reverse=True)


# ---------- Registration ----------

def register(client, headers, reviewer_code, **overrides):
    study_id, _ = any_study()
    body = {"study_id": study_id, "consent_status": "ACTIVE", "reviewer_code": reviewer_code, **overrides}
    return client.post("/api/participants", headers=headers, json=body)


def test_registration_generates_the_next_code_in_the_study(client, coord1, reviewers):
    study_id, _ = any_study()
    expected = next_code(study_id)
    first = register(client, coord1, reviewers[0])
    second = register(client, coord1, reviewers[0])
    assert first.status_code == second.status_code == 201
    assert first.json()["participant_code"] == expected
    assert int(second.json()["participant_code"][2:]) == int(expected[2:]) + 1


def test_new_participant_belongs_to_the_logged_in_coordinator(client, coord1, coord2, coordinators, reviewers):
    body = register(client, coord1, reviewers[1]).json()
    assert body["coordinator_code"] == coordinators[0] and body["reviewer_code"] == reviewers[1]
    new_id = body["participant_id"]
    assert new_id in ids(client.get("/api/participants", headers=coord1))
    assert new_id not in ids(client.get("/api/participants", headers=coord2))
    assert client.get(f"/api/participants/{new_id}", headers=coord2).status_code == 404


def test_client_cannot_choose_the_code_or_the_owner(client, coord1, coordinators, reviewers):
    study_id, _ = any_study()
    expected = next_code(study_id)
    body = register(client, coord1, reviewers[0], participant_code="P-0999",
                    coordinator_code=coordinators[1]).json()
    assert body["participant_code"] == expected
    assert body["coordinator_code"] == coordinators[0]


def test_reviewer_must_be_an_active_reviewer(client, coord1, coordinators):
    for bad_code in ("REV-99", coordinators[1]):
        response = register(client, coord1, bad_code)
        assert response.status_code == 422, bad_code
        assert response.json()["detail"][0]["loc"] == ["body", "reviewer_code"]


def test_inactive_reviewer_cannot_be_assigned(client, coord1, db, reviewers):
    db.execute(text("UPDATE staff_members SET active = FALSE WHERE staff_code = :c"), {"c": reviewers[1]})
    db.commit()
    assert register(client, coord1, reviewers[1]).status_code == 422


def test_unknown_study_returns_404_and_inactive_study_409(client, coord1, db, reviewers):
    assert register(client, coord1, reviewers[0], study_id=999999).status_code == 404
    study_id, _ = any_study()
    db.execute(text("UPDATE studies SET active = FALSE WHERE study_id = :s"), {"s": study_id})
    db.commit()
    assert register(client, coord1, reviewers[0], study_id=study_id).status_code == 409


def test_registration_is_audited_without_personal_data(client, coord1, db, coordinators, reviewers):
    new_id = register(client, coord1, reviewers[0]).json()["participant_id"]
    row = db.execute(text("SELECT action, actor_code, new_value FROM audit_events "
                          "WHERE entity_type='participant' AND entity_id=:i"), {"i": new_id}).one()
    assert tuple(row) == ("PARTICIPANT_ENROLLED", coordinators[0], "ACTIVE")


def test_there_is_no_delete_route_for_participants(client, coord1, coordinators):
    own = one_of(owned_by(coordinators[0]))
    assert client.delete(f"/api/participants/{own}", headers=coord1).status_code == 405


# ---------- Audit events ----------

def test_owner_sees_participant_history_and_others_get_404(client, coord1, coord2, coordinators):
    own = one_of(owned_by(coordinators[0]))
    client.patch(f"/api/participants/{own}/consent", headers=coord1,
                 json={"consent_status": "WITHDRAWN"})
    url = f"/api/audit-events?entity_type=participant&entity_id={own}"
    actions = [e["action"] for e in client.get(url, headers=coord1).json()]
    assert actions[-1] == "CONSENT_CHANGED"
    assert client.get(url, headers=coord2).status_code == 404


def test_review_history_is_visible_only_to_the_assigned_reviewer(client, request, reviewers):
    rows = query("SELECT r.review_id, p.reviewer_code FROM summary_reviews r "
                 "JOIN ai_summaries a USING (summary_id) JOIN visits v USING (visit_id) "
                 "JOIN participants p USING (participant_id) ORDER BY r.review_id LIMIT 1")
    if not rows:
        pytest.skip("Seed has no reviews")
    review_id, owner = rows[0]
    owner_headers = request.getfixturevalue("rev1" if owner == reviewers[0] else "rev2")
    other_headers = request.getfixturevalue("rev2" if owner == reviewers[0] else "rev1")
    url = f"/api/audit-events?entity_type=review&entity_id={review_id}"
    assert client.get(url, headers=owner_headers).status_code == 200
    assert client.get(url, headers=other_headers).status_code == 404


def test_audit_events_cannot_be_changed(db):
    with pytest.raises(Exception, match="append-only"):
        db.execute(text("UPDATE audit_events SET action = 'X' "
                        "WHERE event_id = (SELECT MIN(event_id) FROM audit_events)"))
    db.rollback()