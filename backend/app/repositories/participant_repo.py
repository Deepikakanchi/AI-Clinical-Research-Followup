"""SQL access for participants. Every read is limited by owner_condition(user)."""
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.auth import CurrentUser, owner_condition
from app.db.models import Participant, Visit


def list_scoped(db: Session, user: CurrentUser, study_id: int | None = None) -> list[Participant]:
    query = (
        select(Participant)
        .options(joinedload(Participant.study))
        .where(owner_condition(user))
        .order_by(Participant.study_id, Participant.participant_code)
    )
    if study_id is not None:
        query = query.where(Participant.study_id == study_id)
    return list(db.scalars(query))


def get_scoped(db: Session, user: CurrentUser, participant_id: int,
               for_update: bool = False) -> Participant | None:
    query = (
        select(Participant)
        .options(joinedload(Participant.study))
        .where(Participant.participant_id == participant_id, owner_condition(user))
    )
    if for_update:
        query = query.with_for_update(of=Participant)
    return db.scalar(query)


def next_code_number(db: Session, study_id: int) -> int:
    """Highest P-#### number in the study plus one. Call only while the study row is locked."""
    highest = db.scalar(
        select(func.max(cast(func.substr(Participant.participant_code, 3), Integer)))
        .where(Participant.study_id == study_id)
    )
    return (highest or 0) + 1


def add(db: Session, participant: Participant) -> Participant:
    db.add(participant)
    db.flush()
    return participant


def visits_newest_first(db: Session, participant_id: int) -> list[Visit]:
    return list(db.scalars(
        select(Visit).where(Visit.participant_id == participant_id)
        .order_by(Visit.scheduled_for.desc(), Visit.visit_id.desc())
    ))