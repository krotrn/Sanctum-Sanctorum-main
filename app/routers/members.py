from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.clock import get_now
from app.db import get_db
from app.schemas import LoanOut, LoanStatus, MemberCreate, MemberOut, MemberStats, OrderOut
from app.services import loans as loan_service
from app.services import members as service

router = APIRouter(prefix="/members", tags=["members"])


@router.post("", response_model=MemberOut, status_code=201)
def create_member(data: MemberCreate, db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    return service.create_member(db, data, now)


@router.get("/{member_id}", response_model=MemberOut)
def get_member(member_id: int, db: Session = Depends(get_db)):
    return service.get_member(db, member_id)


@router.get("/{member_id}/orders", response_model=List[OrderOut])
def list_member_orders(member_id: int, db: Session = Depends(get_db)):
    return service.list_member_orders(db, member_id)


@router.get("/{member_id}/stats", response_model=MemberStats)
def get_member_stats(member_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    return service.get_member_stats(db, member_id, now)


@router.get("/{member_id}/loans", response_model=List[LoanOut])
def list_member_loans(
    member_id: int,
    status: Optional[LoanStatus] = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    return loan_service.list_member_loans(db, member_id, now, status)
