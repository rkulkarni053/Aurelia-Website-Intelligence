import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.database import get_db
from backend.app.models.company import Company
from backend.app.models.crawl import Crawl
from backend.app.models.project import Project
from backend.app.models.website import Website
from backend.app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate


router = APIRouter(
    prefix="/api/companies",
    tags=["companies"],
)


@router.post("", response_model=CompanyRead, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Company name is required")

    existing = db.execute(
        select(Company).where(Company.name == name)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Company '{name}' already exists (id: {existing.id})",
        )

    company = Company(name=name, description=payload.description)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("", response_model=list[CompanyRead])
def list_companies(db: Session = Depends(get_db)):
    result = db.execute(
        select(Company).order_by(Company.name.asc())
    )
    return result.scalars().all()


@router.get("/portfolio/all")
def portfolio_all(db: Session = Depends(get_db)):
    """Full history: companies → projects → websites → crawls."""
    companies = db.execute(
        select(Company)
        .options(
            selectinload(Company.projects)
            .selectinload(Project.websites)
            .selectinload(Website.crawls)
        )
        .order_by(Company.name.asc())
    ).scalars().all()

    orphans = db.execute(
        select(Project)
        .where(Project.company_id.is_(None))
        .options(
            selectinload(Project.websites).selectinload(Website.crawls)
        )
        .order_by(Project.created_at.desc())
    ).scalars().all()

    def _crawl_row(c: Crawl) -> dict:
        return {
            "id": str(c.id),
            "status": c.status.value,
            "pages_crawled": c.pages_crawled,
            "pages_discovered": c.pages_discovered,
            "error_message": c.error_message,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        }

    def _website_row(w: Website) -> dict:
        crawls = sorted(w.crawls, key=lambda c: c.created_at, reverse=True)
        return {
            "id": str(w.id),
            "url": w.url,
            "domain": w.domain,
            "role": getattr(w, "role", None) or "primary",
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "crawl_count": len(crawls),
            "latest_crawl_status": crawls[0].status.value if crawls else None,
            "crawls": [_crawl_row(c) for c in crawls],
        }

    def _project_row(p: Project) -> dict:
        websites = sorted(
            p.websites,
            key=lambda w: w.created_at or "",
            reverse=True,
        )
        return {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "status": p.status.value,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "website_count": len(websites),
            "websites": [_website_row(w) for w in websites],
        }

    payload = {
        "companies": [
            {
                "id": str(co.id),
                "name": co.name,
                "description": co.description,
                "created_at": co.created_at.isoformat() if co.created_at else None,
                "project_count": len(co.projects),
                "projects": [
                    _project_row(p)
                    for p in sorted(
                        co.projects,
                        key=lambda p: p.created_at or "",
                        reverse=True,
                    )
                ],
            }
            for co in companies
        ],
        "unassigned_projects": [_project_row(p) for p in orphans],
    }

    total_projects = sum(len(c["projects"]) for c in payload["companies"])
    total_projects += len(payload["unassigned_projects"])
    total_websites = sum(
        p["website_count"]
        for c in payload["companies"]
        for p in c["projects"]
    ) + sum(p["website_count"] for p in payload["unassigned_projects"])
    total_crawls = sum(
        w["crawl_count"]
        for c in payload["companies"]
        for p in c["projects"]
        for w in p["websites"]
    ) + sum(
        w["crawl_count"]
        for p in payload["unassigned_projects"]
        for w in p["websites"]
    )

    payload["summary"] = {
        "companies": len(payload["companies"]),
        "projects": total_projects,
        "websites": total_websites,
        "crawls": total_crawls,
    }
    return payload


@router.get("/{company_id}", response_model=CompanyRead)
def get_company(company_id: uuid.UUID, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.patch("/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Company name is required")
        clash = db.execute(
            select(Company).where(Company.name == name, Company.id != company_id)
        ).scalar_one_or_none()
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"Company '{name}' already exists",
            )
        company.name = name

    if payload.description is not None:
        company.description = payload.description

    db.commit()
    db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: uuid.UUID, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    # Unassign projects so they are not wiped with the company.
    projects = db.execute(
        select(Project).where(Project.company_id == company_id)
    ).scalars().all()
    for project in projects:
        project.company_id = None

    db.delete(company)
    db.commit()
    return None


@router.get("/{company_id}/projects")
def list_company_projects(company_id: uuid.UUID, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    projects = db.execute(
        select(Project)
        .where(Project.company_id == company_id)
        .order_by(Project.created_at.desc())
    ).scalars().all()

    return [
        {
            "id": p.id,
            "company_id": p.company_id,
            "name": p.name,
            "description": p.description,
            "status": p.status.value,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        for p in projects
    ]
