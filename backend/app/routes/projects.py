import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.company import Company
from backend.app.models.project import Project, ProjectStatus
from backend.app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from backend.app.services.workflow import TRANSITIONS, set_project_status


router = APIRouter(
    prefix="/api/projects",
    tags=["projects"],
)


class ProjectStatusUpdate(BaseModel):
    status: ProjectStatus


@router.post(
    "",
    response_model=ProjectRead,
    status_code=201,
)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
):
    company_id = payload.company_id
    if company_id is not None:
        company = db.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")

    project = Project(
        name=payload.name,
        description=payload.description,
        company_id=company_id,
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


@router.get(
    "",
    response_model=list[ProjectRead],
)
def list_projects(
    company_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Project).order_by(Project.created_at.desc())
    if company_id is not None:
        stmt = stmt.where(Project.company_id == company_id)

    result = db.execute(stmt)

    return result.scalars().all()


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Project name is required")
        project.name = name

    if payload.description is not None:
        project.description = payload.description

    if "company_id" in payload.model_fields_set:
        if payload.company_id is not None:
            company = db.get(Company, payload.company_id)
            if company is None:
                raise HTTPException(status_code=404, detail="Company not found")
        project.company_id = payload.company_id

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()
    return None


@router.patch(
    "/{project_id}/status",
    response_model=ProjectRead,
)
def update_project_status(
    project_id: uuid.UUID,
    payload: ProjectStatusUpdate,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        set_project_status(project, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/workflow")
def get_project_workflow(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    current = project.status
    return {
        "project_id": project.id,
        "status": current.value,
        "allowed_next": [s.value for s in TRANSITIONS.get(current, [])],
        "all_statuses": [s.value for s in ProjectStatus],
    }
