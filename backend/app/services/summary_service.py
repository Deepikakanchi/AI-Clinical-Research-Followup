"""Draft generation: retrieve -> prepare -> summarise -> validate -> store (Flow D, US-18 to US-21).

This service can only INSERT into ai_summaries (plus an audit event). It has no
code path that changes consent, visits, notes or review decisions.

Workflow (v2): the AI reads only the latest saved note of the visit, returns up to
5 summary points and proposes up to 3 follow-up actions for the reviewer.

Interfaces used from Person 1:
- app.core.auth: CurrentUser, owner_condition (via summary_repo)
- app.core.errors: NotFoundError, ConflictError
- app.services.audit_service.record(db, entity_type, entity_id, action, actor_code, old_value, new_value)
  adds the audit row to the session without committing.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import null
from sqlalchemy.orm import Session

from app.ai.azure_client import AI_DISABLED, AIError, SummaryClient
from app.ai.prompt import NoteInput, build_known_codes, build_prompt
from app.ai.validator import validate_draft
from app.core.auth import CurrentUser
from app.core.errors import ConflictError, NotFoundError
from app.db.models import AiSummary as AISummary
from app.repositories import summary_repo
from app.schemas.summary import SUMMARY_DRAFT_JSON_SCHEMA, SummaryDraft, SummaryOut
from app.services import audit_service

CONSENT_WITHDRAWN_MESSAGE = "Consent is withdrawn for this participant, so an AI draft cannot be created."
NO_NOTES_MESSAGE = "Add a visit note before requesting an AI draft."
PENDING_DRAFT_MESSAGE = "A draft for this visit is already awaiting review."
ALREADY_APPROVED_MESSAGE = "This visit already has an approved summary."

logger = logging.getLogger("app.ai")


def generate_draft(db: Session, visit_id: int, user: CurrentUser, client: SummaryClient) -> AISummary:
    """Only the participant's own coordinator or assigned reviewer can request a draft."""
    actor_code = user.staff_code
    context = summary_repo.get_draft_context(db, visit_id, user)
    if context is None:
        raise NotFoundError(f"Visit {visit_id} not found")
    visit, participant, study, notes = context

    # Pre-call gates: no provider call is made if any of these fail.
    if participant.consent_status != "ACTIVE":
        raise ConflictError(CONSENT_WITHDRAWN_MESSAGE)
    if not notes:
        raise ConflictError(NO_NOTES_MESSAGE)
    # Only the latest saved note is sent to the AI; each note must be complete on its own.
    notes = [max(notes, key=lambda n: (n.created_at, n.note_id))]
    latest = summary_repo.latest_successful_summary(db, visit_id)
    if latest is not None:
        _, review = latest
        if review is None:
            raise ConflictError(PENDING_DRAFT_MESSAGE)
        if review.decision == "APPROVED":
            raise ConflictError(ALREADY_APPROVED_MESSAGE)

    known_codes = build_known_codes(
        participant.participant_code,
        [visit.coordinator_code, *(n.author_code for n in notes)],
    )
    prepared = build_prompt(
        visit_type=visit.visit_type,
        visit_date=visit.scheduled_for,
        study_title=study.title,
        notes=[NoteInput(n.observation_text, list(n.follow_up_actions or []), n.created_at) for n in notes],
        known_codes=known_codes,
    )

    result = None
    try:
        result = client.generate(prepared.messages, SUMMARY_DRAFT_JSON_SCHEMA)
        draft = validate_draft(result.content, prepared)
    except AIError as err:
        if err.error_code == AI_DISABLED:
            raise  # AI switched off: return 503 straight away, nothing stored
        # Log which check rejected the draft (code + rule only, never note or draft text)
        logger.warning("ai_draft_rejected visit_id=%s error_code=%s rule=%s", visit_id, err.error_code, err)
        _store_failed(db, visit_id, actor_code, client, err, result)
        raise

    summary = summary_repo.insert_summary(
        db,
        visit_id=visit_id,
        generated_draft=draft.model_dump(),
        model_id=result.model_id,
        deployment_name=result.deployment,
        generation_status="SUCCEEDED",
        latency_ms=result.latency_ms,
        error_code=None,
    )
    audit_service.record(db, entity_type="summary", entity_id=summary.summary_id, action="AI_DRAFT_REQUESTED",
                         actor_code=actor_code, old_value=None, new_value="SUCCEEDED")
    db.commit()
    db.refresh(summary)
    return summary


def _store_failed(db: Session, visit_id: int, actor_code: str, client: SummaryClient, err: AIError, result) -> None:
    """FAILED row with no draft text, committed before the error propagates."""
    latency_ms = result.latency_ms if result is not None else err.latency_ms
    model_id = (result.model_id if result is not None else err.model_id) or client.config.deployment
    summary = summary_repo.insert_summary(
        db,
        visit_id=visit_id,
        generated_draft=null(),  # a real SQL NULL, not JSON null, so the FAILED-row CHECK constraint holds
        model_id=model_id,
        deployment_name=client.config.deployment,
        generation_status="FAILED",
        latency_ms=latency_ms,
        error_code=err.error_code,
    )
    audit_service.record(db, entity_type="summary", entity_id=summary.summary_id, action="AI_DRAFT_REQUESTED",
                         actor_code=actor_code, old_value=None, new_value=f"FAILED:{err.error_code}")
    db.commit()


def to_summary_out(summary: AISummary) -> SummaryOut:
    draft: Optional[SummaryDraft] = (
        SummaryDraft.from_stored(summary.generated_draft) if summary.generated_draft else None
    )
    return SummaryOut(
        summary_id=summary.summary_id,
        visit_id=summary.visit_id,
        draft=draft,
        model_id=summary.model_id,
        deployment_name=summary.deployment_name,
        generation_status=summary.generation_status,
        error_code=summary.error_code,
        latency_ms=summary.latency_ms,
        created_at=summary.created_at,
    )


def list_visit_summaries(db: Session, visit_id: int, user: CurrentUser) -> list[SummaryOut]:
    if summary_repo.get_owned_visit(db, visit_id, user) is None:
        raise NotFoundError(f"Visit {visit_id} not found")
    return [to_summary_out(s) for s in summary_repo.list_summaries_for_visit(db, visit_id)]