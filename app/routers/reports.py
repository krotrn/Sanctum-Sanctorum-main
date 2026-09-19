from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import TopBook
from app.services import reports as service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/top-books", response_model=List[TopBook])
def top_books(limit: int = Query(5, ge=1, le=50), db: Session = Depends(get_db)):
    return service.top_books(db, limit)
