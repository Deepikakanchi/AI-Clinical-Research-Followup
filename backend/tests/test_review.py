"""API tests for the draft and review endpoints (US-18, US-21, US-22 to US-27).

Uses Person 1's tests/conftest.py: the database is rebuilt from schema.sql + seed.sql
before every test, users sign in through /api/auth/login, and each participant belongs
to one coordinator and one reviewer. These tests read the rows they need from the seed
instead of hard-coding IDs. The Foundry client is always faked; no Azure call is made.

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
        "visit_summary": "The participant attended a follow-up visit. Mild headache on 2 days this week was reported and BP 128/82 was recorded.",
        "recorded_observations": ["Mild headache on 2 days this week", "BP 128/82 recorded"],
        "follow_up_actions": ["Book follow-up visit in 4 weeks", "Send headache diary template"],
        "missing_information": ["Headache duration is not stated"],
        "follow_up_message_draft": "Staff to book follow-up visit in 4 weeks and send headache diary template.",
        "review_status": "DRAFT",
    }
    draft.update(overrides)
    return json.dumps(draft)


# A reply that is grounded in any seed note: no numbers, no follow-up actions, no blocked words.
SAFE_DRAFT = draft_json(
    visit_summary="The participant attended the visit as recorded in the source note.",
    recorded_observations=[],
    follow_up_actions=[],
    missing_information=["The note does not state a timeframe for follow-up."],
    follow_up_message_draft=None,
)


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


APPROVE = {"decision": "APPROVED", "final_text": "Corrected summary: mild headache on 2 days; BP 128/82.",
           "reviewer_comment": "Tightened wording"}


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


# ------------------------------------------------------ success and failure

def test_successful_draft_is_stored_as_draft_with_audit(client, fake_ai, draftable):
    visit_id, coordinator, _ = draftable
    fake_ai(completion(SAFE_DRAFT))
    response = create_draft(client, visit_id, auth_headers(client, coordinator))
    assert response.status_code == 201
    body = response.json()
    assert body["generation_status"] == "SUCCEEDED" and body["draft"]["review_status"] == "DRAFT"
    events = query("SELECT actor_code, old_value, new_value FROM audit_events "
                   "WHERE entity_type = 'summary' AND entity_id = %s", (body["summary_id"],))
    assert events == [(coordinator, None, "SUCCEEDED")]


@pytest.mark.parametrize(
    "script, status, code",
    [
        (openai.APITimeoutError(request=REQUEST), 504, "TIMEOUT"),
        (completion(draft_json(follow_up_actions=["Start beta blocker"])), 502, "UNGROUNDED_OUTPUT"),
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
    headers = auth_headers(client, draftable[1])
    assert client.patch(f"/api/summaries/{summary_id}/review", json=APPROVE, headers=headers).status_code == 403


def test_unassigned_reviewer_gets_404(client, fake_ai, draftable, reviewers):
    summary_id = make_draft(client, fake_ai, draftable)
    headers = auth_headers(client, other(reviewers, draftable[2]))
    assert client.patch(f"/api/summaries/{summary_id}/review", json=APPROVE, headers=headers).status_code == 404


def test_assigned_reviewer_approval_keeps_original_draft(client, fake_ai, draftable):
    summary_id = make_draft(client, fake_ai, draftable)
    original = query("SELECT generated_draft FROM ai_summaries WHERE summary_id = %s", (summary_id,))
    headers = auth_headers(client, draftable[2])
    response = client.patch(f"/api/summaries/{summary_id}/review", json=APPROVE, headers=headers)
    assert response.status_code == 200 and response.json()["decision"] == "APPROVED"
    assert query("SELECT generated_draft FROM ai_summaries WHERE summary_id = %s", (summary_id,)) == original

    detail = client.get(f"/api/summaries/{summary_id}", headers=headers).json()
    assert detail["review_state"] == "APPROVED"
    assert detail["summary"]["draft"]["visit_summary"] != detail["review"]["final_text"]
    assert len(detail["source_notes"]) >= 1


def test_second_review_returns_409(client, fake_ai, draftable):
    summary_id = make_draft(client, fake_ai, draftable)
    headers = auth_headers(client, draftable[2])
    url = f"/api/summaries/{summary_id}/review"
    assert client.patch(url, json=APPROVE, headers=headers).status_code == 200
    assert client.patch(url, json=APPROVE, headers=headers).status_code == 409


def test_reject_needs_comment_then_allows_new_draft(client, fake_ai, draftable):
    summary_id = make_draft(client, fake_ai, draftable)
    reviewer = auth_headers(client, draftable[2])
    url = f"/api/summaries/{summary_id}/review"
    assert client.patch(url, json={"decision": "REJECTED"}, headers=reviewer).status_code == 422
    rejected = client.patch(url, json={"decision": "REJECTED", "reviewer_comment": "Misses BP context"},
                            headers=reviewer)
    assert rejected.status_code == 200
    fake_ai(completion(SAFE_DRAFT))
    assert create_draft(client, draftable[0], auth_headers(client, draftable[1])).status_code == 201


def test_follow_up_flag_is_saved(client, fake_ai, draftable):
    summary_id = make_draft(client, fake_ai, draftable)
    body = {**APPROVE, "follow_up_flag": True}
    response = client.patch(f"/api/summaries/{summary_id}/review", json=body,
                            headers=auth_headers(client, draftable[2]))
    assert response.status_code == 200 and response.json()["follow_up_flag"] is True


def test_review_queue_is_scoped_to_the_assigned_reviewer(client, fake_ai, draftable, reviewers):
    summary_id = make_draft(client, fake_ai, draftable)
    assigned = auth_headers(client, draftable[2])
    unassigned = auth_headers(client, other(reviewers, draftable[2]))

    assert summary_id in [item["summary_id"] for item in client.get("/api/review-queue", headers=assigned).json()]
    assert summary_id not in [item["summary_id"] for item in client.get("/api/review-queue", headers=unassigned).json()]

    client.patch(f"/api/summaries/{summary_id}/review", json=APPROVE, headers=assigned)
    assert summary_id not in [item["summary_id"] for item in client.get("/api/review-queue", headers=assigned).json()]


def test_review_queue_needs_sign_in(client):
    assert client.get("/api/review-queue").status_code == 401