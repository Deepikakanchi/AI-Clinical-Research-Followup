"""Automatic API checks for Person 2 (visits, notes, dashboard, review queue).

Runs against the RUNNING backend and your normal database (no test database needed).
It changes data, so reset the database first:

    psql -U postgres -d clinical_followup -f database/schema.sql
    psql -U postgres -d clinical_followup -f database/seed.sql

Then, with uvicorn running, from the backend folder:

    python scripts/check_person2_api.py
"""
import sys

import httpx

BASE = "http://127.0.0.1:8000"
PASSWORD = "Demo@2026"
results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("  PASS  " if condition else "  FAIL  ") + name + ("" if condition else f"   -> {detail}"))


def login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    if r.status_code != 200:
        print(f"Login failed for {email}: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    body = r.json()
    token = body.get("token") or body.get("access_token")
    return {"Authorization": f"Bearer {token}"}, body


def ids(response):
    try:
        return [v["visit_id"] for v in response.json()]
    except Exception:
        return response.text[:150]


def main():
    try:
        httpx.get(BASE + "/api/health", timeout=5)
    except httpx.HTTPError:
        print("Cannot reach the backend. Start it first:  uvicorn app.main:app --reload")
        sys.exit(1)

    c = httpx.Client(base_url=BASE, timeout=20)

    print("\nTest 2: login protection")
    r = c.get("/api/visits")
    check("2a no token -> 401", r.status_code == 401, r.status_code)
    C1, body = login(c, "coord.01@example.org")
    check("2b coordinator login, role COORDINATOR", body.get("role") == "COORDINATOR", body)

    print("\nTest 3: visit list and filters (coordinator 1 owns study STD-SLEEP-01)")
    r = c.get("/api/visits", headers=C1)
    check("3  all -> 10 own visits", sorted(ids(r)) == [1, 2, 3, 4, 8, 9, 12, 13, 15, 16], ids(r))
    r = c.get("/api/visits", params={"view": "overdue"}, headers=C1)
    check("3a overdue -> 13", ids(r) == [13], ids(r))
    r = c.get("/api/visits", params={"view": "due"}, headers=C1)
    check("3b due -> 15, 16", ids(r) == [15, 16], ids(r))
    r = c.get("/api/visits", params={"view": "follow_up"}, headers=C1)
    check("3c follow_up -> 9, 12, 13", ids(r) == [9, 12, 13], ids(r))
    r = c.get("/api/visits", params={"status": "COMPLETED"}, headers=C1)
    check("3d COMPLETED -> 1, 2, 3, 4, 8", sorted(ids(r)) == [1, 2, 3, 4, 8], ids(r))
    r = c.get("/api/visits", params={"status": "MISSED"}, headers=C1)
    check("3e MISSED -> 9, 12", sorted(ids(r)) == [9, 12], ids(r))
    r = c.get("/api/visits", params={"participant_id": 1}, headers=C1)
    check("3f participant 1 -> 1, 2, 15", sorted(ids(r)) == [1, 2, 15], ids(r))
    r = c.get("/api/visits", params={"status": "DONE"}, headers=C1)
    check("3g invalid status -> 422", r.status_code == 422, r.status_code)

    print("\nTest 4: visit detail")
    for vid, notes, state in [(1, 1, "APPROVED"), (2, 2, "APPROVED"), (3, 2, "AWAITING_REVIEW"),
                              (4, 1, "REJECTED"), (15, 0, "NO_NOTES")]:
        r = c.get(f"/api/visits/{vid}", headers=C1)
        ok = r.status_code == 200 and r.json()["draft_state"] == state and len(r.json()["notes"]) == notes
        check(f"4  visit {vid} -> {state}, {notes} note(s)", ok, r.text[:150])
    check("4f visit 14 (coordinator 2's) -> 404", c.get("/api/visits/14", headers=C1).status_code == 404)
    check("4g visit 999 -> 404", c.get("/api/visits/999", headers=C1).status_code == 404)

    print("\nTest 5: dashboard")
    expected = {"active_participants": 5, "scheduled": 3, "due_7_days": 2, "overdue": 1, "completed": 5,
                "missed": 2, "cancelled": 0, "open_follow_up_actions": 8, "awaiting_review": 1}
    r = c.get("/api/reports/follow-ups", headers=C1)
    check("5a counts", r.json() == expected, r.json())
    r = c.get("/api/reports/follow-ups", params={"study_id": 2}, headers=C1)
    check("5b study 2 (not yours) -> all 0", set(r.json().values()) == {0}, r.json())
    r = c.get("/api/reports/follow-ups", params={"study_id": 1}, headers=C1)
    check("5c study 1 -> same as 5a", r.json() == expected, r.json())

    print("\nTest 6: follow-up view and review queue")
    r = c.get("/api/reports/follow-up-items", headers=C1).json()
    check("6a missed/overdue -> 9, 12, 13", [v["visit_id"] for v in r["missed_or_overdue_visits"]] == [9, 12, 13],
          r["missed_or_overdue_visits"])
    check("6a notes with actions -> 6", len(r["notes_with_actions"]) == 6, len(r["notes_with_actions"]))
    check("6a flagged -> summary 2", [f["summary_id"] for f in r["flagged_summaries"]] == [2], r["flagged_summaries"])
    r = c.get("/api/review-queue", headers=C1)
    check("6b review queue -> summary 5", [q["summary_id"] for q in r.json()] == [5], r.text[:150])

    print("\nTest 7: booking visits")
    new = {"participant_id": 1, "scheduled_for": "2026-12-20T10:00:00Z", "visit_type": "FOLLOW_UP"}
    r = c.post("/api/visits", json=new, headers=C1)
    check("7a book -> 201, coordinator COORD-01", r.status_code == 201 and r.json()["coordinator_code"] == "COORD-01",
          r.text[:150])
    new_id = r.json().get("visit_id") if r.status_code == 201 else 21
    r = c.post("/api/visits", json=new, headers=C1)
    check("7b same participant, same time -> 409", r.status_code == 409, r.text[:120])
    r = c.post("/api/visits", json={**new, "participant_id": 2}, headers=C1)
    check("7c same coordinator, same time -> 409", r.status_code == 409, r.text[:120])
    r = c.post("/api/visits", json={**new, "participant_id": 5, "scheduled_for": "2026-12-21T10:00:00Z"}, headers=C1)
    check("7d withdrawn consent -> 409", r.status_code == 409, r.text[:120])
    r = c.post("/api/visits", json={**new, "participant_id": 7, "scheduled_for": "2026-12-21T10:00:00Z"}, headers=C1)
    check("7e another coordinator's participant -> 404", r.status_code == 404, r.text[:120])
    r = c.post("/api/visits", json={**new, "scheduled_for": "2020-01-01T10:00:00Z"}, headers=C1)
    check("7f past date -> 422", r.status_code == 422, r.status_code)
    r = c.post("/api/visits", json={**new, "scheduled_for": "2026-12-22T10:00:00Z", "visit_type": "CHECKUP"}, headers=C1)
    check("7g invalid visit type -> 422", r.status_code == 422, r.status_code)
    r = c.post("/api/visits", json={**new, "scheduled_for": "2026-12-22T10:00:00Z", "coordinator_code": "REV-01"},
               headers=C1)
    check("7h reviewer as coordinator -> 422", r.status_code == 422, r.status_code)
    r = c.post("/api/visits", json={**new, "scheduled_for": "2026-12-22T10:00:00Z", "name": "John"}, headers=C1)
    check("7i extra field -> 422", r.status_code == 422, r.status_code)

    print("\nTest 8: changing visits")
    p = lambda vid, body: c.patch(f"/api/visits/{vid}", json=body, headers=C1)
    check("8a future visit -> COMPLETED 409", p(new_id, {"status": "COMPLETED"}).status_code == 409)
    check("8b future visit -> MISSED 409", p(new_id, {"status": "MISSED"}).status_code == 409)
    r = p(13, {"status": "MISSED"})
    check("8c overdue visit 13 -> MISSED 200", r.status_code == 200 and r.json()["status"] == "MISSED", r.text[:120])
    check("8d closed visit 13 -> CANCELLED 409", p(13, {"status": "CANCELLED"}).status_code == 409)
    check("8e completed visit 1 -> CANCELLED 409", p(1, {"status": "CANCELLED"}).status_code == 409)
    r = p(new_id, {"scheduled_for": "2026-12-23T11:00:00Z"})
    check("8f reschedule -> 200", r.status_code == 200, r.text[:120])
    check("8g reschedule to the past -> 422", p(new_id, {"scheduled_for": "2020-01-01T10:00:00Z"}).status_code == 422)
    r = p(16, {"status": "CANCELLED"})
    check("8h cancel visit 16 -> 200", r.status_code == 200 and r.json()["status"] == "CANCELLED", r.text[:120])
    check("8i empty change -> 422", p(new_id, {}).status_code == 422)

    print("\nTest 9: notes")
    note = {"observation_text": "Participant returned the diary for all 7 days.", "follow_up_actions": ["Book next visit"]}
    r = c.post(f"/api/visits/{new_id}/notes", json=note, headers=C1)
    check("9a note on scheduled visit -> 409", r.status_code == 409, r.text[:120])
    r = c.post("/api/visits/1/notes", json={"observation_text": "Too short"}, headers=C1)
    check("9b short note -> 422", r.status_code == 422, r.status_code)
    r = c.post("/api/visits/1/notes", json={**note, "name": "John"}, headers=C1)
    check("9c extra field -> 422", r.status_code == 422, r.status_code)
    r = c.post("/api/visits/1/notes", json=note, headers=C1)
    check("9d note on completed visit -> 201 by COORD-01",
          r.status_code == 201 and r.json()["author_code"] == "COORD-01", r.text[:120])
    new_note = r.json().get("note_id") if r.status_code == 201 else None
    r = c.get("/api/visits/1/notes", headers=C1)
    check("9e 2 notes, oldest first", len(r.json()) == 2 and r.json()[-1]["note_id"] == new_note, r.text[:150])
    check("9f notes of another coordinator's visit -> 404",
          c.get("/api/visits/14/notes", headers=C1).status_code == 404)

    print("\nTest 10: dashboard after the changes")
    r = c.get("/api/reports/follow-ups", headers=C1).json()
    after = {"scheduled": 2, "due_7_days": 1, "overdue": 0, "missed": 3, "cancelled": 1,
             "open_follow_up_actions": 9, "completed": 5}
    check("10 counts updated", all(r[k] == v for k, v in after.items()), r)

    print("\nTest 11: ownership (coordinator 2)")
    C2, _ = login(c, "coord.02@example.org")
    r = c.get("/api/visits", headers=C2)
    check("11a only study 2 visits", sorted(ids(r)) == [5, 6, 7, 10, 11, 14, 17, 18, 19, 20], ids(r))
    check("11b visit 1 -> 404", c.get("/api/visits/1", headers=C2).status_code == 404)
    check("11c change visit 15 -> 404",
          c.patch("/api/visits/15", json={"status": "CANCELLED"}, headers=C2).status_code == 404)
    check("11d notes of visit 1 -> 404", c.get("/api/visits/1/notes", headers=C2).status_code == 404)
    r = c.get("/api/visits/6", headers=C2)
    check("11e visit 6 -> DRAFT_UNAVAILABLE", r.status_code == 200 and r.json()["draft_state"] == "DRAFT_UNAVAILABLE",
          r.text[:120])
    expected2 = {"active_participants": 5, "scheduled": 4, "due_7_days": 0, "overdue": 1, "completed": 3,
                 "missed": 2, "cancelled": 1, "open_follow_up_actions": 4, "awaiting_review": 1}
    r = c.get("/api/reports/follow-ups", headers=C2)
    check("11f coordinator 2 dashboard", r.json() == expected2, r.json())

    print("\nTest 12: reviewer rules")
    R1, body = login(c, "rev.01@example.org")
    check("12a reviewer login, role REVIEWER", body.get("role") == "REVIEWER", body)
    check("12b reviewer can read visits", c.get("/api/visits", headers=R1).status_code == 200)
    r = c.post("/api/visits", json={**new, "scheduled_for": "2026-12-24T10:00:00Z"}, headers=R1)
    check("12c reviewer books a visit -> 403", r.status_code == 403, r.status_code)
    check("12d reviewer changes a visit -> 403",
          c.patch("/api/visits/15", json={"status": "CANCELLED"}, headers=R1).status_code == 403)
    check("12e reviewer adds a note -> 403",
          c.post("/api/visits/1/notes", json=note, headers=R1).status_code == 403)
    r = c.get("/api/review-queue", headers=R1)
    check("12f reviewer 1 queue -> summary 5", [q["summary_id"] for q in r.json()] == [5], r.text[:120])
    R2, _ = login(c, "rev.02@example.org")
    r = c.get("/api/review-queue", headers=R2)
    check("12g reviewer 2 queue -> summary 6", [q["summary_id"] for q in r.json()] == [6], r.text[:120])

    print("\nTest 13: audit trail (Person 1's endpoint)")
    r = c.get("/api/audit-events", params={"entity_type": "visit", "entity_id": 13}, headers=C1)
    check("13 visit 13 status change is audited", r.status_code == 200 and "VISIT_STATUS_CHANGED" in r.text,
          r.text[:150])

    passed = sum(results)
    print(f"\n{passed} of {len(results)} checks passed")
    print("Reset the database again before your demo (schema.sql, then seed.sql).")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()