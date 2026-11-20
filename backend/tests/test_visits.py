"""Scheduling, transitions, notes, dashboard and audit.  (US-10 to US-16, US-28, US-30)"""
from datetime import datetime, timedelta, timezone

from tests.conftest import COORD, REV


def future(days=30, hour=9):
    d = datetime.now(timezone.utc) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def test_schedule_visit(client, db_conn):
    r = client.post("/api/visits", json={"participant_id": 1, "scheduled_for": future(),
                                          "visit_type": "FOLLOW_UP", "coordinator_code": "COORD-01"}, headers=COORD)
    assert r.status_code == 201
    v = r.json()
    assert v["status"] == "SCHEDULED" and v["participant_code"] == "P-0001"
    assert db_conn.execute("SELECT action FROM audit_events WHERE entity_type='visit' AND entity_id=%s",
                           (v["visit_id"],)).fetchone() == ("VISIT_SCHEDULED",)


def test_past_date_and_bad_type_422(client):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    r = client.post("/api/visits", json={"participant_id": 1, "scheduled_for": past, "visit_type": "FOLLOW_UP",
                                          "coordinator_code": "COORD-01"}, headers=COORD)
    assert r.status_code == 422 and r.json()["detail"][0]["field"] == "scheduled_for"
    r = client.post("/api/visits", json={"participant_id": 1, "scheduled_for": future(), "visit_type": "CHECKUP",
                                          "coordinator_code": "COORD-01"}, headers=COORD)
    assert r.status_code == 422


def test_withdrawn_participant_cannot_be_scheduled(client):
    r = client.post("/api/visits", json={"participant_id": 5, "scheduled_for": future(), "visit_type": "FOLLOW_UP",
                                          "coordinator_code": "COORD-01"}, headers=COORD)
    assert r.status_code == 409 and r.json()["code"] == "CONSENT_WITHDRAWN"


def test_reviewer_cannot_be_coordinator(client):
    r = client.post("/api/visits", json={"participant_id": 1, "scheduled_for": future(), "visit_type": "FOLLOW_UP",
                                          "coordinator_code": "REV-01"}, headers=COORD)
    assert r.status_code == 422


def test_duplicate_times_409_name_the_clashing_visit(client):
    v15 = client.get("/api/visits/15").json()   # P-0001 with COORD-01
    r = client.post("/api/visits", json={"participant_id": 1, "scheduled_for": v15["scheduled_for"],
                                          "visit_type": "FOLLOW_UP", "coordinator_code": "COORD-02"}, headers=COORD)
    assert r.status_code == 409 and "visit 15" in r.json()["detail"]
    r = client.post("/api/visits", json={"participant_id": 2, "scheduled_for": v15["scheduled_for"],
                                          "visit_type": "FOLLOW_UP", "coordinator_code": "COORD-01"}, headers=COORD)
    assert r.status_code == 409 and "COORD-01" in r.json()["detail"]


def test_cancelled_slot_can_be_rebooked(client):
    v20 = client.get("/api/visits/20").json()   # CANCELLED, COORD-01
    r = client.post("/api/visits", json={"participant_id": 11, "scheduled_for": v20["scheduled_for"],
                                          "visit_type": "FOLLOW_UP", "coordinator_code": "COORD-01"}, headers=COORD)
    assert r.status_code == 201


def test_status_transition_rules(client, db_conn):
    assert client.patch("/api/visits/17", json={"status": "COMPLETED"}, headers=COORD).status_code == 409  # future
    assert client.patch("/api/visits/17", json={"status": "MISSED"}, headers=COORD).status_code == 409     # future
    r = client.patch("/api/visits/13", json={"status": "MISSED"}, headers=COORD)                            # overdue
    assert r.status_code == 200 and r.json()["status"] == "MISSED"
    assert db_conn.execute("SELECT old_value, new_value FROM audit_events WHERE action='VISIT_STATUS_CHANGED' "
                           "AND entity_id=13").fetchone() == ("SCHEDULED", "MISSED")
    assert client.patch("/api/visits/1", json={"status": "CANCELLED"}, headers=COORD).status_code == 409    # closed
    assert client.patch("/api/visits/17", json={"status": "CANCELLED"}, headers=COORD).status_code == 200


def test_reschedule_and_reviewer_forbidden(client):
    r = client.patch("/api/visits/18", json={"scheduled_for": future(40, 11)}, headers=COORD)
    assert r.status_code == 200
    assert client.patch("/api/visits/18", json={"status": "CANCELLED"}, headers=REV).status_code == 403


def test_due_and_overdue_labels_come_from_the_api(client):
    labels = {v["visit_id"]: v["due_label"] for v in client.get("/api/visits").json()}
    assert labels[13] == "OVERDUE" and labels[14] == "OVERDUE"
    assert labels[15] == "DUE" and labels[16] == "DUE"
    assert labels[17] is None and labels[1] is None
    assert {v["visit_id"] for v in client.get("/api/visits", params={"view": "overdue"}).json()} == {13, 14}
    assert {v["visit_id"] for v in client.get("/api/visits", params={"view": "due"}).json()} == {15, 16}
    assert len(client.get("/api/visits", params={"study_id": 1, "status": "COMPLETED"}).json()) == 5


def test_dashboard_matches_sql_and_updates(client):
    report = client.get("/api/reports/follow-ups").json()
    assert report == {"active_participants": 10, "scheduled": 7, "due_7_days": 2, "overdue": 2, "completed": 8,
                      "missed": 4, "cancelled": 1, "open_follow_up_actions": 12, "awaiting_review": 2}
    client.patch("/api/visits/14", json={"status": "COMPLETED"}, headers=COORD)
    after = client.get("/api/reports/follow-ups").json()
    assert (after["completed"], after["overdue"], after["scheduled"]) == (9, 1, 6)
    assert client.get("/api/reports/follow-ups", params={"study_id": 2}).json()["active_participants"] == 5


def test_notes_rules(client, db_conn):
    note = {"observation_text": "Participant returned the diary for all 7 days.", "follow_up_actions": ["Book next visit"]}
    assert client.post("/api/visits/15/notes", json=note, headers=COORD).status_code == 409        # SCHEDULED
    assert client.post("/api/visits/1/notes", json={"observation_text": "Too short"},
                       headers=COORD).status_code == 422
    first = db_conn.execute("SELECT observation_text FROM visit_notes WHERE note_id=1").fetchone()
    r = client.post("/api/visits/1/notes", json=note, headers=COORD)
    assert r.status_code == 201 and r.json()["author_code"] == "COORD-01"
    notes = client.get("/api/visits/1/notes").json()
    assert [n["note_id"] for n in notes][-1] == r.json()["note_id"] and len(notes) == 2          # oldest first
    assert db_conn.execute("SELECT observation_text FROM visit_notes WHERE note_id=1").fetchone() == first


def test_visit_detail_draft_states(client):
    assert client.get("/api/visits/1").json()["draft_state"] == "APPROVED"
    assert client.get("/api/visits/4").json()["draft_state"] == "REJECTED"
    assert client.get("/api/visits/3").json()["draft_state"] == "AWAITING_REVIEW"
    assert client.get("/api/visits/6").json()["draft_state"] == "DRAFT_UNAVAILABLE"
    assert client.get("/api/visits/15").json()["draft_state"] == "NO_NOTES"
    assert client.get("/api/visits/999").status_code == 404


def test_follow_up_items_and_audit_trail(client):
    items = client.get("/api/reports/follow-up-items").json()
    assert {v["visit_id"] for v in items["missed_or_overdue_visits"]} == {9, 10, 11, 12, 13, 14}
    assert [f["summary_id"] for f in items["flagged_summaries"]] == [2]
    events = client.get("/api/audit-events", params={"entity_type": "visit", "entity_id": 2}).json()
    assert [e["action"] for e in events] == ["VISIT_SCHEDULED", "VISIT_STATUS_CHANGED"]