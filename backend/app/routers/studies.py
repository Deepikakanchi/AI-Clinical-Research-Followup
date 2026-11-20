"""GET /api/studies (both roles) and POST /api/studies (coordinators). US-06."""
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
    return [StudyOut.model_validate(s) for s in study_repo.list_all(db)]


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