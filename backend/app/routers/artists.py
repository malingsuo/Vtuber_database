from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas
from app.deps import get_company_id, get_db
from app.models import Artist

router = APIRouter(prefix="/artists", tags=["藝人"])


def _get_or_404(db: Session, cid: int, artist_id: int) -> Artist:
    artist = db.scalar(
        select(Artist).where(Artist.id == artist_id, Artist.company_id == cid)
    )
    if artist is None:
        raise HTTPException(404, "找不到這位藝人")
    return artist


@router.get("", response_model=list[schemas.ArtistOut])
def list_artists(
    db: Session = Depends(get_db), cid: int = Depends(get_company_id)
):
    return db.scalars(
        select(Artist).where(Artist.company_id == cid).order_by(Artist.id)
    ).all()


@router.post("", response_model=schemas.ArtistOut, status_code=201)
def create_artist(
    body: schemas.ArtistCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    artist = Artist(company_id=cid, **body.model_dump())
    db.add(artist)
    db.commit()
    return artist


@router.get("/{artist_id}", response_model=schemas.ArtistOut)
def get_artist(
    artist_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    return _get_or_404(db, cid, artist_id)


@router.put("/{artist_id}", response_model=schemas.ArtistOut)
def update_artist(
    artist_id: int,
    body: schemas.ArtistUpdate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    artist = _get_or_404(db, cid, artist_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(artist, key, value)
    db.commit()
    return artist


@router.delete("/{artist_id}", status_code=204)
def delete_artist(
    artist_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    artist = _get_or_404(db, cid, artist_id)
    db.delete(artist)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "這位藝人已有商品或熱度紀錄，不能刪除；可改成「畢業」狀態")
