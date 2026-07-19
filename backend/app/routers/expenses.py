from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.deps import get_company_id, get_db
from app.models import Artist, Event, Expense

router = APIRouter(prefix="/expenses", tags=["檔期開支"])


@router.get("", response_model=list[schemas.ExpenseOut])
def list_expenses(
    event_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    return db.scalars(
        select(Expense)
        .where(Expense.company_id == cid, Expense.event_id == event_id)
        .order_by(Expense.id)
    ).all()


@router.post("", response_model=schemas.ExpenseOut, status_code=201)
def create_expense(
    body: schemas.ExpenseCreate,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    if not db.scalar(
        select(Event.id).where(Event.id == body.event_id, Event.company_id == cid)
    ):
        raise HTTPException(422, "找不到指定的活動")
    if body.artist_id is not None and not db.scalar(
        select(Artist.id).where(Artist.id == body.artist_id, Artist.company_id == cid)
    ):
        raise HTTPException(422, "找不到指定的藝人")
    expense = Expense(company_id=cid, **body.model_dump())
    db.add(expense)
    db.commit()
    return expense


@router.delete("/{expense_id}", status_code=204)
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    cid: int = Depends(get_company_id),
):
    expense = db.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.company_id == cid)
    )
    if expense is None:
        raise HTTPException(404, "找不到這筆開支")
    db.delete(expense)
    db.commit()
