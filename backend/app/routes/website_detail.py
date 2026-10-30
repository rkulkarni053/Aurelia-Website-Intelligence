import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.website import Website
from backend.app.schemas.website import WebsiteRead

router = APIRouter(
    prefix="/api/websites",
    tags=["websites"],
)


@router.get("", response_model=list[WebsiteRead])
def list_all_websites(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Website).order_by(Website.created_at.desc())
    ).scalars().all()
    return rows


@router.get("/{website_id}", response_model=WebsiteRead)
def get_website(
    website_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    website = db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")
    return website
