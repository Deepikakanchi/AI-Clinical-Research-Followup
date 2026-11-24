"""
routers/studies.py - Study endpoints owned by Rajnish Maurya .  (US-06)
GET /api/studies (both roles) and POST /api/studies (coordinators only).

Registered in main.py with: app.include_router(studies.router)
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import COORDINATOR, CurrentUser, get_current_user, require_role
from app.core.errors import ConflictError
from app.db.models import Study
from app.db.session import get_db
from app.repositories import study_repo
from app.schemas.study import StudyCreate, StudyOut
from app.services import audit_service

router = APIRouter(prefix="/api/studies", tags=["Studies"])


@router.get("", response_model=list[StudyOut])
def list_studies(db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)) -> list[StudyOut]:
    # Studies are shared reference data, needed by everyone's dropdowns.
    # Counts are totals across all coordinators plus the caller's own share.
    counts = study_repo.participant_counts(db, user)
    result = []
    for study in study_repo.list_all(db):
        total, active, mine = counts.get(study.study_id, (0, 0, 0))
        result.append(StudyOut.model_validate(study).model_copy(update={
            "participant_count": total,
            "active_participant_count": active,
            "my_participant_count": mine,
        }))
    return result


@router.post("", response_model=StudyOut, status_code=status.HTTP_201_CREATED)
def create_study(body: StudyCreate, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(require_role(COORDINATOR))) -> StudyOut:
    if study_repo.get_by_code(db, body.study_code) is not None:
        raise ConflictError(f"A study with code {body.study_code} already exists")
    study = study_repo.add(db, Study(**body.model_dump()))
    audit_service.record(db, entity_type="study", entity_id=study.study_id,
                         action="STUDY_CREATED", actor_code=user.staff_code,
                         new_value=study.study_code)
    db.commit()
    db.refresh(study)
    return StudyOut.model_validate(study)