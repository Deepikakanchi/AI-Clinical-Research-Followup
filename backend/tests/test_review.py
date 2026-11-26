"""API tests for the draft and review endpoints (US-18, US-21, US-22 to US-27).

Uses Person 1's tests/conftest.py: the database is rebuilt from schema.sql + seed.sql
before every test, users sign in through /api/auth/login, and each participant belongs
to one coordinator and one reviewer. These tests read the rows they need from the seed
instead of hard-coding IDs. The Foundry client is always faked; no Azure call is made.

Workflow (v2):
- Drafts have up to 5 summary points and at most 3 proposed follow-up actions.
- APPROVED needs final text, a comment and at least one follow-up action.
- REJECTED needs at least one reason and stores no follow-up actions.

Run from backend/:  python -m pytest tests/test_review.py -v
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.ai.azure_client import AIConfig, SummaryClient
from app.routers.summaries import get_summary_client
from conftest import auth_headers, query

# ------------------------------------------------------- fake Foundry client
# Mimics client.chat.completions.create() so no test ever calls Azure.

REQUEST = httpx.Request("POST", "https://example.openai.azure.com/openai/v1/chat/completions")


class FakeSDK:
    """Mimics client.chat.completions.create(). Each scripted item is a reply or an exception;
    the last item repeats once the script runs out."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item


def completion(content=None, finish_reason="stop", model="gpt-5.4-mini-2026-03-17", refusal=None):
    message = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(model=model, choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def make_client(*script, **config):
    cfg = AIConfig(endpoint="https://example.openai.azure.com/", deployment="clinical-summary",
                   api_key="test-key", **config)
    sdk = FakeSDK(*script)
    return SummaryClient(cfg, client=sdk), sdk


def draft_json(**overrides) -> str:
    draft = {
        "summary_points": ["The participant attended the visit as recorded in the source note."],
        "follow_up_actions": ["Book the next follow-up visit"],
        "review_status": "DRAFT",
    }
    draft.update(overrides)
    return json.dumps(draft)


# A reply that is grounded in any seed note: no numbers and no blocked words.
SAFE_DRAFT = draft_json()


# ------------------------------------------------------------ seed lookups

def find_visit(extra_sql: str, *, consent: str = "ACTIVE", with_notes: bool = True) -> tuple[int, str, str]:
    """(visit_id, coordinator_code, reviewer_code) for the first seed visit matching the conditions."""
    notes = "EXISTS" if with_notes else "NOT EXISTS"
    rows = query(
        f"""SELECT v.visit_id, p.coordinator_code, p.reviewer_code
            FROM visits v JOIN participants p ON p.participant_id = v.participant_id
            WHERE p.consent_status = %s
              AND {notes} (SELECT 1 FROM visit_notes n WHERE n.visit_id = v.visit_id)
              {extra_sql}
            ORDER BY v.visit_id LIMIT 1""",
        (consent,),
    )
    if not rows:
        pytest.skip("seed.sql has no visit matching this test's conditions")
    return rows[0]


NO_OPEN_DRAFT = """
  AND v.status = 'COMPLETED'
  AND NOT EXISTS (SELECT 1 FROM ai_summaries s
                  LEFT JOIN summary_reviews r ON r.summary_id = s.summary_id
                  WHERE s.visit_id = v.visit_id AND s.generation_status = 'SUCCEEDED'
                    AND (r.review_id IS NULL OR r.decision = 'APPROVED'))"""


@pytest.fixture
def draftable():
    """A completed visit with notes, ACTIVE consent and no open or approved draft."""
    return find_visit(NO_OPEN_DRAFT)


@pytest.fixture
def fake_ai(app):
    """Installs a scripted fake Foundry client for the duration of one test."""
    def install(*script, **config):
        client, sdk = make_client(*script, **config)
        app.dependency_overrides[get_summary_client] = lambda: client
        return sdk
    yield install
    app.dependency_overrides.pop(get_summary_client, None)


def summaries_for(visit_id: int) -> list[tuple]:
    return query("SELECT summary_id, generation_status, generated_draft, error_code FROM ai_summaries "
                 "WHERE visit_id = %s ORDER BY summary_id", (visit_id,))


def other(codes: list[str], not_this: str) -> str:
    choices = [c for c in codes if c != not_this]
    if not choices:
        pytest.skip("seed.sql needs a second staff member of this role")
    return choices[0]


def create_draft(client, visit_id, headers):
    return client.post(f"/api/visits/{visit_id}/draft-summary", headers=headers)


def make_draft(client, fake_ai, draftable) -> int:
    visit_id, coordinator, _ = draftable
    fake_ai(completion(SAFE_DRAFT))
    response = create_draft(client, visit_id, auth_headers(client, coordinator))
    assert response.status_code == 201, response.text
    return response.json()["summary_id"]


APPROVE = {"decision": "APPROVED",
           "final_text": "Corrected summary: the participant attended and the diary was returned.",
           "reviewer_comment": "Checked against the source note and tightened the wording.",
           "follow_up_actions": ["Book the next follow-up visit", "Send the next diary template"]}
REJECT = {"decision": "REJECTED", "rejection_reasons": ["Sleep hours are not recorded", "The diary entries are missing"]}


def review(client, summary_id, body, headers):
    return client.patch(f"/api/summaries/{summary_id}/review", json=body, headers=headers)


# ------------------------------------------------------ pre-call gates (US-18)

def test_withdrawn_consent_returns_409_and_makes_no_call(client, fake_ai):
    visit_id, coordinator, _ = find_visit("", consent="WITHDRAWN")
    before = summaries_for(visit_id)
    sdk = fake_ai(completion(SAFE_DRAFT))
    response = create_draft(client, visit_id, auth_headers(client, coordinator))
    assert response.status_code == 409 and "Consent is withdrawn" in response.json()["detail"]
    assert sdk.calls == [] and summaries_for(visit_id) == before


def test_visit_without_notes_returns_409(client, fake_ai):
    visit_id, coordinator, _ = find_visit("", with_notes=False)
    sdk = fake_ai(completion(SAFE_DRAFT))
    assert create_draft(client, visit_id, auth_headers(client, coordinator)).status_code == 409
    assert sdk.calls == []


def test_unknown_visit_returns_404(client, fake_ai, coord1):
    fake_ai(completion(SAFE_DRAFT))
    assert create_draft(client, 999999, coord1).status_code == 404


def test_other_coordinators_visit_returns_404_and_makes_no_call(client, fake_ai, draftable, coordinators):
    visit_id, owner, _ = draftable
    sdk = fake_ai(completion(SAFE_DRAFT))
    response = create_draft(client, visit_id, auth_headers(client, other(coordinators, owner)))
    assert response.status_code == 404 and sdk.calls == []


def test_no_token_returns_401(client, fake_ai, draftable):
    fake_ai(completion(SAFE_DRAFT))
    assert create_draft(client, draftable[0], {}).status_code == 401


def test_outgoing_prompt_contains_no_codes(client, fake_ai, draftable):
    visit_id, coordinator, reviewer = draftable
    sdk = fake_ai(completion(SAFE_DRAFT))
    assert create_draft(client, visit_id, auth_headers(client, coordinator)).status_code == 201
    sent = json.dumps(sdk.calls[0]["messages"])
    participant_code = query("SELECT p.participant_code FROM visits v JOIN participants p "
                             "ON p.participant_id = v.participant_id WHERE v.visit_id = %s", (visit_id,))[0][0]
    for code in (participant_code, coordinator, reviewer):
        assert code not in sent


def test_only_the_latest_note_is_sent(client, fake_ai, draftable):
    visit_id, coordinator, _ = draftable
    headers = auth_headers(client, coordinator)
    latest = "Latest observation only: the participant returned the device in good condition."
    assert client.post(f"/api/visits/{visit_id}/notes", json={"observation_text": latest}, headers=headers).status_code == 201
    sdk = fake_ai(completion(SAFE_DRAFT))
    assert create_draft(client, visit_id, headers).status_code == 201
    user_message = sdk.calls[0]["messages"][1]["content"]
    assert latest in user_message and "Note 2" not in user_message


# ------------------------------------------------------ success and failure

def test_successful_draft_is_stored_as_draft_with_audit(client, fake_ai, draftable):
    visit_id, coordinator, _ = draftable
    fake_ai(completion(SAFE_DRAFT))
    response = create_draft(client, visit_id, auth_headers(client, coordinator))
    assert response.status_code == 201
    body = response.json()
    assert body["generation_status"] == "SUCCEEDED" and body["draft"]["review_status"] == "DRAFT"
    assert body["draft"]["summary_points"] and len(body["draft"]["follow_up_actions"]) <= 3
    events = query("SELECT actor_code, old_value, new_value FROM audit_events "
                   "WHERE entity_type = 'summary' AND entity_id = %s", (body["summary_id"],))
    assert events == [(coordinator, None, "SUCCEEDED")]


@pytest.mark.parametrize(
    "script, status, code",
    [
        (openai.APITimeoutError(request=REQUEST), 504, "TIMEOUT"),
        (completion(draft_json(follow_up_actions=["Prescribe a beta blocker"])), 502, "UNGROUNDED_OUTPUT"),
        (completion(draft_json(follow_up_actions=["Book visit", "Send diary", "Check device", "File form"])), 502, "INVALID_OUTPUT"),
        (completion("not json"), 502, "INVALID_OUTPUT"),
        (completion(draft_json(), finish_reason="content_filter"), 502, "CONTENT_FILTER"),
    ],
)
def test_failures_store_failed_row_without_text(client, fake_ai, draftable, script, status, code):
    visit_id, coordinator, _ = draftable
    before = len(summaries_for(visit_id))
    fake_ai(script)
    response = create_draft(client, visit_id, auth_headers(client, coordinator))
    assert response.status_code == status
    assert response.json()["detail"] == "Draft unavailable, try again later"
    rows = summaries_for(visit_id)
    assert len(rows) == before + 1
    _, generation_status, generated_draft, error_code = rows[-1]
    assert generation_status == "FAILED" and generated_draft is None and error_code == code


def test_ai_disabled_returns_503_and_stores_nothing(client, fake_ai, draftable):
    visit_id, coordinator, _ = draftable
    before = summaries_for(visit_id)
    fake_ai(completion(SAFE_DRAFT), enabled=False)
    assert create_draft(client, visit_id, auth_headers(client, coordinator)).status_code == 503
    assert summaries_for(visit_id) == before


def test_draft_endpoint_changes_no_consent_visits_notes_or_reviews(client, fake_ai, draftable):
    """US-27: the AI route can only insert into ai_summaries (and audit_events)."""
    def snapshot():
        return (
            query("SELECT participant_id, consent_status FROM participants ORDER BY participant_id"),
            query("SELECT visit_id, status, scheduled_for FROM visits ORDER BY visit_id"),
            query("SELECT COUNT(*) FROM summary_reviews"),
            query("SELECT COUNT(*) FROM visit_notes"),
        )
    visit_id, coordinator, _ = draftable
    before = snapshot()
    fake_ai(completion(SAFE_DRAFT))
    assert create_draft(client, visit_id, auth_headers(client, coordinator)).status_code == 201
    assert snapshot() == before


def test_new_draft_blocked_while_one_awaits_review(client, fake_ai, draftable):
    visit_id, coordinator, _ = draftable
    headers = auth_headers(client, coordinator)
    fake_ai(completion(SAFE_DRAFT))
    assert create_draft(client, visit_id, headers).status_code == 201
    assert create_draft(client, visit_id, headers).status_code == 409


# --------------------------------------------------------- review (US-22 to US-27)

def test_coordinator_cannot_approve(client, fake_ai, draftable):
    summary_id = make_draft(client, fake_ai, draftable)
    assert review(client, summary_id, APPROVE, auth_headers(client, draftable[1])).status_code == 403


def test_unassigned_reviewer_gets_404(client, fake_ai, draftable, reviewers):
    summary_id = make_draft(client, fake_ai, draftable)
    headers = auth_headers(client, other(reviewers, draftable[2]))
    assert review(client, summary_id, APPROVE, headers).status_code == 404


@pytest.mark.parametrize("missing", ["reviewer_comment", "follow_up_actions", "final_text"])
def test_approve_needs_text_comment_and_actions(client, fake_ai, draftable, missing):
    summary_id = make_draft(client, fake_ai, draftable)
    body = {k: v for k, v in APPROVE.items() if k != missing}
    response = review(client, summary_id, body, auth_headers(client, draftable[2]))
    assert response.status_code == 422
    assert query("SELECT COUNT(*) FROM summary_reviews WHERE summary_id = %s", (summary_id,)) == [(0,)]


def test_approval_stores_reviewer_actions_and_keeps_original_draft(client, fake_ai, draftable):
    summary_id = make_draft(client, fake_ai, draftable)
    original = query("SELECT generated_draft FROM ai_summaries WHERE summary_id = %s", (summary_id,))
    headers = auth_headers(client, draftable[2])
    response = review(client, summary_id, APPROVE, headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "APPROVED"
    assert body["final_follow_up_actions"] == APPROVE["follow_up_actions"]   # AI's action kept + one added
    assert body["reviewer_comment"] == APPROVE["reviewer_comment"] and body["rejection_reasons"] == []
    assert query("SELECT generated_draft FROM ai_summaries WHERE summary_id = %s", (summary_id,)) == original

    detail = client.get(f"/api/summaries/{summary_id}", headers=headers).json()
    assert detail["review_state"] == "APPROVED"
    assert detail["summary"]["draft"]["follow_up_actions"] == ["Book the next follow-up visit"]
    assert detail["review"]["final_follow_up_actions"] == APPROVE["follow_up_actions"]
    assert len(detail["source_notes"]) >= 1


def test_reject_needs_reasons_and_stores_no_actions(client, fake_ai, draftable):
    summary_id = make_draft(client, fake_ai, draftable)
    reviewer = auth_headers(client, draftable[2])
    assert review(client, summary_id, {"decision": "REJECTED", "reviewer_comment": "Not usable"}, reviewer).status_code == 422
    rejected = review(client, summary_id, {**REJECT, "follow_up_actions": ["ignored"], "final_text": "ignored text here"}, reviewer)
    assert rejected.status_code == 200, rejected.text
    body = rejected.json()
    assert body["rejection_reasons"] == REJECT["rejection_reasons"]
    assert body["final_follow_up_actions"] == [] and body["final_text"] is None
    fake_ai(completion(SAFE_DRAFT))   # a rejected draft allows a new one
    assert create_draft(client, draftable[0], auth_headers(client, draftable[1])).status_code == 201


def test_second_review_returns_409(client, fake_ai, draftable):
    summary_id = make_draft(client, fake_ai, draftable)
    headers = auth_headers(client, draftable[2])
    assert review(client, summary_id, APPROVE, headers).status_code == 200
    assert review(client, summary_id, APPROVE, headers).status_code == 409


def test_follow_up_flag_is_saved(client, fake_ai, draftable):
    summary_id = make_draft(client, fake_ai, draftable)
    response = review(client, summary_id, {**APPROVE, "follow_up_flag": True}, auth_headers(client, draftable[2]))
    assert response.status_code == 200 and response.json()["follow_up_flag"] is True


def test_approved_actions_appear_in_follow_ups_and_dashboard(client, fake_ai, draftable):
    summary_id = make_draft(client, fake_ai, draftable)
    coordinator = auth_headers(client, draftable[1])
    before = client.get("/api/reports/follow-ups", headers=coordinator).json()["open_follow_up_actions"]
    assert review(client, summary_id, APPROVE, auth_headers(client, draftable[2])).status_code == 200
    after = client.get("/api/reports/follow-ups", headers=coordinator).json()["open_follow_up_actions"]
    assert after == before + len(APPROVE["follow_up_actions"])
    items = client.get("/api/reports/follow-up-items", headers=coordinator).json()["approved_actions"]
    assert any(i["summary_id"] == summary_id and i["follow_up_actions"] == APPROVE["follow_up_actions"] for i in items)


def test_review_queue_is_scoped_to_the_assigned_reviewer(client, fake_ai, draftable, reviewers):
    summary_id = make_draft(client, fake_ai, draftable)
    assigned = auth_headers(client, draftable[2])
    unassigned = auth_headers(client, other(reviewers, draftable[2]))

    assert summary_id in [item["summary_id"] for item in client.get("/api/review-queue", headers=assigned).json()]
    assert summary_id not in [item["summary_id"] for item in client.get("/api/review-queue", headers=unassigned).json()]

    review(client, summary_id, APPROVE, assigned)
    assert summary_id not in [item["summary_id"] for item in client.get("/api/review-queue", headers=assigned).json()]


def test_review_queue_needs_sign_in(client):
    assert client.get("/api/review-queue").status_code == 401


def test_seeded_drafts_and_reviews_use_the_new_format(client, rev1):
    detail = client.get("/api/summaries/2", headers=rev1).json()
    assert len(detail["summary"]["draft"]["summary_points"]) == 5
    assert len(detail["review"]["final_follow_up_actions"]) == 3


# ------------------------------------------------------------------ notes (v2)

def test_notes_take_observations_only(client, draftable):
    visit_id, coordinator, _ = draftable
    headers = auth_headers(client, coordinator)
    url = f"/api/visits/{visit_id}/notes"
    ok = client.post(url, json={"observation_text": "The participant returned the sleep diary today."}, headers=headers)
    assert ok.status_code == 201 and ok.json()["follow_up_actions"] == []
    with_actions = {"observation_text": "The participant returned the sleep diary today.", "follow_up_actions": ["Book visit"]}
    assert client.post(url, json=with_actions, headers=headers).status_code == 422
    assert client.post(url, json={"observation_text": "x" * 16001}, headers=headers).status_code == 422
    assert client.post(url, json={"observation_text": "Long but allowed. " + "y" * 15000}, headers=headers).status_code == 201