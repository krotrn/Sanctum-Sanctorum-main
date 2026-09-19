from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.clock import get_now
from app.db import get_db
from app.schemas import LoanCreate, LoanOut
from app.services import loans as service

router = APIRouter(prefix="/loans", tags=["loans"])


@router.post("", response_model=LoanOut, status_code=201)
def create_loan(data: LoanCreate, db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    return service.create_loan(db, data, now)


@router.get("/{loan_id}", response_model=LoanOut)
def get_loan(loan_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    return service.get_loan(db, loan_id, now)


@router.post("/{loan_id}/return", response_model=LoanOut)
def return_loan(loan_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    return service.return_loan(db, loan_id, now)
