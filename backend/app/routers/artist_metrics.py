from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.deps import get_company_id, get_db
from app.models import Artist, ArtistMetric

router = APIRouter(prefix="/artist-metrics", tags=["藝人熱度"])


@router.get("", response_model=list[schemas.ArtistMetricOut])
def list_metrics(
    artist_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    return db.scalars(
        select(ArtistMetric)
        .where(ArtistMetric.company_id == cid, ArtistMetric.artist_id == artist_id)
        .order_by(ArtistMetric.record_date.desc(), ArtistMetric.id.desc())
    ).all()


@router.post("", response_model=schemas.ArtistMetricOut, status_code=201)
def create_metric(
    body: schemas.ArtistMetricCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    if not db.scalar(
        select(Artist.id).where(
            Artist.id == body.artist_id, Artist.company_id == cid
        )
    ):
        raise HTTPException(422, "找不到指定的藝人")
    metric = ArtistMetric(company_id=cid, **body.model_dump())
    db.add(metric)
    db.commit()
    return metric


@router.delete("/{metric_id}", status_code=204)
def delete_metric(
    metric_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    metric = db.scalar(
        select(ArtistMetric).where(
            ArtistMetric.id == metric_id, ArtistMetric.company_id == cid
        )
    )
    if metric is None:
        raise HTTPException(404, "找不到這筆紀錄")
    db.delete(metric)
    db.commit()
