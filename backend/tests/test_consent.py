"""
tests/test_consent.py - Consent change tests, owned by Rajnish Maurya.  (US-09)

Run from the backend folder with: pytest tests/test_consent.py
"""
from sqlalchemy import text

from tests.conftest import owned_by, query


def own_active(coordinator: str) -> int:
    rows = query("SELECT participant_id FROM participants WHERE coordinator_code = %s "
                 "AND consent_status = 'ACTIVE' ORDER BY participant_id LIMIT 1", (coordinator,))
    assert rows, "Seed needs an ACTIVE participant for each coordinator"
    return rows[0][0]


def test_owner_withdraws_consent_and_it_is_audited(client, coord1, db, coordinators):
    pid = own_active(coordinators[0])
    before = client.get(f"/api/participants/{pid}", headers=coord1).json()["consent_updated_at"]
    response = client.patch(f"/api/participants/{pid}/consent", headers=coord1,
                            json={"consent_status": "WITHDRAWN", "reason": "Participant asked to stop"})
    assert response.status_code == 200
    body = response.json()
    assert body["consent_status"] == "WITHDRAWN"
    assert body["consent_updated_at"] > before

    row = db.execute(text("SELECT action, actor_code, old_value, new_value FROM audit_events "
                          "WHERE entity_type='participant' AND entity_id=:p AND action='CONSENT_CHANGED' "
                          "ORDER BY event_id DESC LIMIT 1"), {"p": pid}).one()
    assert tuple(row) == ("CONSENT_CHANGED", coordinators[0], "ACTIVE", "WITHDRAWN")


def test_reason_text_is_never_stored(client, coord1, db, coordinators):
    pid = own_active(coordinators[0])
    client.patch(f"/api/participants/{pid}/consent", headers=coord1,
                 json={"consent_status": "WITHDRAWN", "reason": "SECRET-REASON-TEXT"})
    hits = db.execute(text("SELECT COUNT(*) FROM audit_events WHERE old_value LIKE '%SECRET%' "
                           "OR new_value LIKE '%SECRET%' OR action LIKE '%SECRET%'")).scalar()
    assert hits == 0


def test_consent_can_be_withdrawn_and_reactivated(client, coord1, coordinators):
    pid = own_active(coordinators[0])
    assert client.patch(f"/api/participants/{pid}/consent", headers=coord1,
                        json={"consent_status": "WITHDRAWN"}).status_code == 200
    response = client.patch(f"/api/participants/{pid}/consent", headers=coord1,
                            json={"consent_status": "ACTIVE"})
    assert response.status_code == 200 and response.json()["consent_status"] == "ACTIVE"


def test_setting_the_same_value_returns_409(client, coord1, coordinators):
    pid = own_active(coordinators[0])
    response = client.patch(f"/api/participants/{pid}/consent", headers=coord1,
                            json={"consent_status": "ACTIVE"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Consent is already ACTIVE"


def test_reviewer_cannot_change_consent(client, rev1, coordinators):
    pid = own_active(coordinators[0])
    response = client.patch(f"/api/participants/{pid}/consent", headers=rev1,
                            json={"consent_status": "WITHDRAWN"})
    assert response.status_code == 403


def test_other_coordinator_cannot_change_consent(client, coord2, db, coordinators):
    pid = own_active(coordinators[0])
    response = client.patch(f"/api/participants/{pid}/consent", headers=coord2,
                            json={"consent_status": "WITHDRAWN"})
    assert response.status_code == 404
    status = db.execute(text("SELECT consent_status FROM participants WHERE participant_id=:p"),
                        {"p": pid}).scalar()
    assert status == "ACTIVE"


def test_invalid_consent_value_returns_422(client, coord1, coordinators):
    pid = own_active(coordinators[0])
    response = client.patch(f"/api/participants/{pid}/consent", headers=coord1,
                            json={"consent_status": "PAUSED"})
    assert response.status_code == 422