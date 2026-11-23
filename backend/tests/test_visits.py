"""
tests/test_visits.py - Scheduling, transitions, notes, dashboard and audit tests, owned by Person 2.
(US-10 to US-16, US-28, US-30)

By default every request is sent as COORD-01 (see the client fixture below).
Seed ownership (database/seed.sql):
  COORD-01 owns participants 1-6  -> visits 1, 2, 3, 4, 8, 9, 12, 13, 15, 16
  COORD-02 owns participants 7-12 -> visits 5, 6, 7, 10, 11, 14, 17, 18, 19, 20
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from tests.conftest import COORD, COORD2, REV


@pytest.fixture
def client(app):
    """Logged in as COORD-01 by default; pass headers=... to act as someone else."""
    with TestClient(app, headers=COORD) as test_client:
        yield test_client


def future(days=30, hour=9):
    d = datetime.now(timezone.utc) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def test_schedule_visit(client, db_conn):
    r = client.post("/api/visits", json={"participant_id": 1, "scheduled_for": future(),
                                          "visit_type": "FOLLOW_UP", "coordinator_code": "COORD-01"})
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["status"] == "SCHEDULED" and v["participant_code"] == "P-0001"
    assert db_conn.execute("SELECT action FROM audit_events WHERE entity_type='visit' AND entity_id=%s",
                           (v["visit_id"],)).fetchone() == ("VISIT_SCHEDULED",)


def test_past_date_and_bad_type_422(client):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    r = client.post("/api/visits", json={"participant_id": 1, "scheduled_for": past, "visit_type": "FOLLOW_UP",
                                          "coordinator_code": "COORD-01"})
    assert r.status_code == 422 and "scheduled_for" in str(r.json()["detail"])
    r = client.post("/api/visits", json={"participant_id": 1, "scheduled_for": future(), "visit_type": "CHECKUP",
                                          "coordinator_code": "COORD-01"})
    assert r.status_code == 422


def test_withdrawn_participant_cannot_be_scheduled(client):
    # Participant 5 is WITHDRAWN and owned by COORD-01.
    r = client.post("/api/visits", json={"participant_id": 5, "scheduled_for": future(), "visit_type": "FOLLOW_UP",
                                          "coordinator_code": "COORD-01"})
    assert r.status_code == 409 and r.json().get("code") == "CONSENT_WITHDRAWN"


def test_other_coordinators_participant_is_not_found(client):
    # Participant 7 belongs to COORD-02, so COORD-01 cannot book for it.
    r = client.post("/api/visits", json={"participant_id": 7, "scheduled_for": future(), "visit_type": "FOLLOW_UP",
                                          "coordinator_code": "COORD-01"})
    assert r.status_code == 404


def test_reviewer_cannot_be_coordinator(client):
    r = client.post("/api/visits", json={"participant_id": 1, "scheduled_for": future(), "visit_type": "FOLLOW_UP",
                                          "coordinator_code": "REV-01"})
    assert r.status_code in (403, 422)


def test_duplicate_times_409_name_the_clashing_visit(client):
    v15 = client.get("/api/visits/15").json()          # P-0001, COORD-01, SCHEDULED
    r = client.post("/api/visits", json={"participant_id": 1, "scheduled_for": v15["scheduled_for"],
                                          "visit_type": "FOLLOW_UP", "coordinator_code": "COORD-01"})
    assert r.status_code == 409 and "15" in r.json()["detail"]
    r = client.post("/api/visits", json={"participant_id": 3, "scheduled_for": v15["scheduled_for"],
                                          "visit_type": "FOLLOW_UP", "coordinator_code": "COORD-01"})
    assert r.status_code == 409


def test_cancelled_slot_can_be_rebooked(client):
    v20 = client.get("/api/visits/20", headers=COORD2).json()   # CANCELLED, COORD-02
    r = client.post("/api/visits", json={"participant_id": 12, "scheduled_for": v20["scheduled_for"],
                                          "visit_type": "FOLLOW_UP", "coordinator_code": "COORD-02"}, headers=COORD2)
    assert r.status_code == 201, r.text


def test_status_transition_rules(client, db_conn):
    assert client.patch("/api/visits/15", json={"status": "COMPLETED"}).status_code == 409   # future
    assert client.patch("/api/visits/15", json={"status": "MISSED"}).status_code == 409      # future
    r = client.patch("/api/visits/13", json={"status": "MISSED"})                             # overdue
    assert r.status_code == 200 and r.json()["status"] == "MISSED"
    assert db_conn.execute("SELECT old_value, new_value FROM audit_events WHERE action='VISIT_STATUS_CHANGED' "
                           "AND entity_id=13").fetchone() == ("SCHEDULED", "MISSED")
    assert client.patch("/api/visits/1", json={"status": "CANCELLED"}).status_code == 409     # closed
    assert client.patch("/api/visits/15", json={"status": "CANCELLED"}).status_code == 200


def test_reschedule_and_reviewer_forbidden(client):
    r = client.patch("/api/visits/15", json={"scheduled_for": future(40, 11)})
    assert r.status_code == 200, r.text
    assert client.patch("/api/visits/15", json={"status": "CANCELLED"}, headers=REV).status_code == 403


def test_other_coordinators_visit_is_not_found(client):
    assert client.get("/api/visits/17").status_code == 404                     # COORD-02's visit
    assert client.patch("/api/visits/17", json={"status": "CANCELLED"}).status_code == 404


def test_due_and_overdue_labels_come_from_the_api(client):
    labels = {v["visit_id"]: v["due_label"] for v in client.get("/api/visits").json()}
    assert set(labels) == {1, 2, 3, 4, 8, 9, 12, 13, 15, 16}                 # only COORD-01's visits
    assert labels[13] == "OVERDUE"
    assert labels[15] == "DUE" and labels[16] == "DUE"
    assert labels[1] is None and labels[12] is None
    assert {v["visit_id"] for v in client.get("/api/visits", params={"view": "overdue"}).json()} == {13}
    assert {v["visit_id"] for v in client.get("/api/visits", params={"view": "due"}).json()} == {15, 16}
    assert len(client.get("/api/visits", params={"study_id": 1, "status": "COMPLETED"}).json()) == 5


def test_dashboard_matches_sql_and_updates(client):
    report = client.get("/api/reports/follow-ups").json()
    assert report == {"active_participants": 5, "scheduled": 3, "due_7_days": 2, "overdue": 1, "completed": 5,
                      "missed": 2, "cancelled": 0, "open_follow_up_actions": 8, "awaiting_review": 1}
    client.patch("/api/visits/13", json={"status": "COMPLETED"})
    after = client.get("/api/reports/follow-ups").json()
    assert (after["completed"], after["overdue"], after["scheduled"]) == (6, 0, 2)
    # COORD-01 has no participants in study 2; COORD-02 sees its own.
    assert client.get("/api/reports/follow-ups", params={"study_id": 2}).json()["active_participants"] == 0
    assert client.get("/api/reports/follow-ups", params={"study_id": 2},
                      headers=COORD2).json()["active_participants"] == 5


def test_notes_rules(client, db_conn):
    note = {"observation_text": "Participant returned the diary for all 7 days.", "follow_up_actions": ["Book next visit"]}
    assert client.post("/api/visits/15/notes", json=note).status_code == 409          # SCHEDULED
    assert client.post("/api/visits/1/notes", json={"observation_text": "Too short"}).status_code == 422
    first = db_conn.execute("SELECT observation_text FROM visit_notes WHERE note_id=1").fetchone()
    r = client.post("/api/visits/1/notes", json=note)
    assert r.status_code == 201 and r.json()["author_code"] == "COORD-01"
    notes = client.get("/api/visits/1/notes").json()
    assert [n["note_id"] for n in notes][-1] == r.json()["note_id"] and len(notes) == 2   # oldest first
    assert db_conn.execute("SELECT observation_text FROM visit_notes WHERE note_id=1").fetchone() == first


def test_visit_detail_draft_states(client):
    assert client.get("/api/visits/1").json()["draft_state"] == "APPROVED"
    assert client.get("/api/visits/4").json()["draft_state"] == "REJECTED"
    assert client.get("/api/visits/3").json()["draft_state"] == "AWAITING_REVIEW"
    assert client.get("/api/visits/6", headers=COORD2).json()["draft_state"] == "DRAFT_UNAVAILABLE"
    assert client.get("/api/visits/15").json()["draft_state"] == "NO_NOTES"
    assert client.get("/api/visits/999").status_code == 404


def test_follow_up_items_and_audit_trail(client):
    items = client.get("/api/reports/follow-up-items").json()
    assert {v["visit_id"] for v in items["missed_or_overdue_visits"]} == {9, 12, 13}
    assert [f["summary_id"] for f in items["flagged_summaries"]] == [2]
    events = client.get("/api/audit-events", params={"entity_type": "visit", "entity_id": 2}).json()
    assert [e["action"] for e in events] == ["VISIT_SCHEDULED", "VISIT_STATUS_CHANGED"]


def test_requests_without_login_are_rejected(app):
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/visits").status_code == 401
        assert anonymous.get("/api/reports/follow-ups").status_code == 401