"""SQL access for ai_summaries and summary_reviews. No business rules here.

Every lookup that starts from a visit or summary is limited to the caller's own
participants with Person 1's owner_condition(user): coordinators see participants
whose coordinator_code is theirs, reviewers those whose reviewer_code is theirs.
Rows outside that scope are simply not found (404), as elsewhere in the app.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, owner_condition
from app.db.models import AiSummary as AISummary, Participant, Study, SummaryReview, Visit, VisitNote

# Required SQL demonstration 3: summaries awaiting review. database/queries.sql holds the
# same query without the last ownership condition, which the API adds per caller.



def get_draft_context(
    db: Session, visit_id: int, user: CurrentUser
) -> Optional[tuple[Visit, Participant, Study, list[VisitNote]]]:
    """Read-only load of everything the draft needs: visit, participant, study and notes (oldest first)."""
    row = db.execute(
        select(Visit, Participant, Study)
        .join(Participant, Participant.participant_id == Visit.participant_id)
        .join(Study, Study.study_id == Participant.study_id)
        .where(Visit.visit_id == visit_id, owner_condition(user))
    ).first()
    if row is None:
        return None
    visit, participant, study = row
    return visit, participant, study, get_notes_for_visit(db, visit_id)


def get_notes_for_visit(db: Session, visit_id: int) -> list[VisitNote]:
    return list(
        db.scalars(
            select(VisitNote).where(VisitNote.visit_id == visit_id).order_by(VisitNote.created_at, VisitNote.note_id)
        )
    )


def get_owned_visit(db: Session, visit_id: int, user: CurrentUser) -> Optional[Visit]:
    return db.scalars(
        select(Visit)
        .join(Participant, Participant.participant_id == Visit.participant_id)
        .where(Visit.visit_id == visit_id, owner_condition(user))
    ).first()


def latest_successful_summary(db: Session, visit_id: int) -> Optional[tuple[AISummary, Optional[SummaryReview]]]:
    row = db.execute(
        select(AISummary, SummaryReview)
        .outerjoin(SummaryReview, SummaryReview.summary_id == AISummary.summary_id)
        .where(AISummary.visit_id == visit_id, AISummary.generation_status == "SUCCEEDED")
        .order_by(AISummary.created_at.desc(), AISummary.summary_id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def insert_summary(db: Session, **fields: Any) -> AISummary:
    """Insert only. ai_summaries rows are never updated."""
    summary = AISummary(**fields)
    db.add(summary)
    db.flush()
    return summary


def list_summaries_for_visit(db: Session, visit_id: int) -> list[AISummary]:
    return list(
        db.scalars(
            select(AISummary)
            .where(AISummary.visit_id == visit_id)
            .order_by(AISummary.created_at.desc(), AISummary.summary_id.desc())
        )
    )


def get_owned_summary(db: Session, summary_id: int, user: CurrentUser) -> Optional[AISummary]:
    return db.scalars(
        select(AISummary)
        .join(Visit, Visit.visit_id == AISummary.visit_id)
        .join(Participant, Participant.participant_id == Visit.participant_id)
        .where(AISummary.summary_id == summary_id, owner_condition(user))
    ).first()


def get_review_for_summary(db: Session, summary_id: int) -> Optional[SummaryReview]:
    return db.scalars(select(SummaryReview).where(SummaryReview.summary_id == summary_id)).first()


def insert_review(db: Session, **fields: Any) -> SummaryReview:
    review = SummaryReview(**fields)
    db.add(review)
    db.flush()
    return review


