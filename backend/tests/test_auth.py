"""
tests/test_auth.py - Login, role redirect and role-check tests, owned by Rajnish Maurya.  (US-27)

Run from the backend folder with: pytest tests/test_auth.py
"""
from sqlalchemy import text

from tests.conftest import TEST_PASSWORD, email_of, login


def test_coordinator_login_returns_token_role_and_dashboard_path(client, coordinators):
    response = login(client, coordinators[0])
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "COORDINATOR"
    assert body["staff_code"] == coordinators[0]
    assert body["home_path"] == "/coordinator/dashboard"
    assert body["token_type"] == "bearer" and body["token"]
    assert "password" not in str(body).lower()


def test_reviewer_login_redirects_to_review_queue(client, reviewers):
    body = login(client, reviewers[0]).json()
    assert body["role"] == "REVIEWER"
    assert body["home_path"] == "/reviewer/queue"


def test_email_is_not_case_sensitive(client, coordinators):
    email = "  " + email_of(coordinators[0]).upper() + " "
    response = client.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200


def test_password_is_case_sensitive(client, coordinators):
    assert login(client, coordinators[0], TEST_PASSWORD.upper()).status_code == 401


def test_wrong_password_and_unknown_email_get_the_same_generic_401(client, coordinators):
    wrong_password = login(client, coordinators[0], "wrong-password")
    unknown_email = client.post("/api/auth/login",
                                json={"email": "nobody@study.test", "password": TEST_PASSWORD})
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "Email or password is incorrect"}


def test_missing_password_or_bad_email_returns_422(client):
    assert client.post("/api/auth/login", json={"email": "a@study.test", "password": ""}).status_code == 422
    response = client.post("/api/auth/login", json={"email": "not-an-email", "password": "x"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "email"]


def test_overlong_password_is_rejected_safely(client, coordinators):
    assert login(client, coordinators[0], "é" * 100).status_code == 401


def test_inactive_staff_cannot_log_in(client, db, coordinators):
    db.execute(text("UPDATE staff_members SET active = FALSE WHERE staff_code = :c"), {"c": coordinators[1]})
    db.commit()
    assert login(client, coordinators[1]).status_code == 401


def test_deactivated_staff_lose_access_with_an_existing_token(client, db, coord2, coordinators):
    assert client.get("/api/participants", headers=coord2).status_code == 200
    db.execute(text("UPDATE staff_members SET active = FALSE WHERE staff_code = :c"), {"c": coordinators[1]})
    db.commit()
    assert client.get("/api/participants", headers=coord2).status_code == 401


def test_staff_details_are_reloaded_from_the_database_on_every_request(client, db, rev1, reviewers):
    assert client.get("/api/auth/me", headers=rev1).json()["role"] == "REVIEWER"
    # The token holds only the staff code; role and label are read from the database each time.
    db.execute(text("UPDATE staff_members SET display_label = 'Renamed' WHERE staff_code = :c"),
               {"c": reviewers[0]})
    db.commit()
    assert client.get("/api/auth/me", headers=rev1).json()["display_label"] == "Renamed"


def test_requests_without_or_with_bad_token_get_401(client):
    assert client.get("/api/participants").status_code == 401
    bad = client.get("/api/participants", headers={"Authorization": "Bearer not.a.token"})
    assert bad.status_code == 401


def test_me_returns_current_user_and_home_path(client, rev1, reviewers):
    body = client.get("/api/auth/me", headers=rev1).json()
    assert body["staff_code"] == reviewers[0]
    assert body["role"] == "REVIEWER" and body["home_path"] == "/reviewer/queue"


def test_reviewer_cannot_use_coordinator_actions(client, rev1, reviewers):
    assert client.post("/api/studies", headers=rev1, json={
        "study_code": "STD-NEW-01", "title": "A new study", "study_type": "REGISTRY"}).status_code == 403
    assert client.post("/api/participants", headers=rev1, json={
        "study_id": 1, "consent_status": "ACTIVE", "reviewer_code": reviewers[0]}).status_code == 403
    assert client.get("/api/staff", headers=rev1).status_code == 403


def test_staff_list_gives_coordinators_reviewers_only_without_login_details(client, coord1, reviewers):
    body = client.get("/api/staff", headers=coord1).json()
    assert [s["staff_code"] for s in body] == reviewers
    assert all("email" not in s and "password_hash" not in s for s in body)


def test_health_is_public(client):
    assert client.get("/api/health").json()["database"] == "up"