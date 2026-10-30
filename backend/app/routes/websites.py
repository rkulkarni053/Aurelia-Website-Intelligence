import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.project import Project
from backend.app.models.website import Website
from backend.app.schemas.website import WebsiteCreate, WebsiteRead


router = APIRouter(
    prefix="/api/projects/{project_id}/websites",
    tags=["websites"],
)


@router.post(
    "",
    response_model=WebsiteRead,
    status_code=201,
)
def create_website(
    project_id: uuid.UUID,
    payload: WebsiteCreate,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    url = str(payload.url)
    domain = (urlparse(url).hostname or "").lower()

    existing = db.execute(
        select(Website).where(
            Website.project_id == project_id,
            Website.domain == domain,
        )
    ).scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Website {domain} already exists in this project "
            f"(id: {existing.id})",
        )

    role = getattr(payload, "role", None) or "primary"
    if role not in {"primary", "competitor"}:
        raise HTTPException(status_code=400, detail="role must be primary or competitor")

    website = Website(
        project_id=project_id,
        url=url,
        domain=domain,
        role=role,
    )

    db.add(website)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Website {domain} already exists in this project",
        )

    db.refresh(website)

    return website


@router.get(
    "",
    response_model=list[WebsiteRead],
)
def list_websites(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    result = db.execute(
        select(Website)
        .where(Website.project_id == project_id)
        .order_by(Website.created_at.desc())
    )

    return result.scalars().all()
