from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import BookCreate, BookOut, BookPage, BookSort
from app.services import books as service

router = APIRouter(prefix="/books", tags=["books"])


@router.post("", response_model=BookOut, status_code=201)
def create_book(data: BookCreate, db: Session = Depends(get_db)):
    return service.create_book(db, data)


@router.get("", response_model=BookPage)
def list_books(
    q: Optional[str] = None,
    restricted: Optional[bool] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    sort: Optional[BookSort] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_books(
        db,
        q=q,
        restricted=restricted,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/{book_id}", response_model=BookOut)
def get_book(book_id: int, db: Session = Depends(get_db)):
    return service.get_book(db, book_id)


# TODO: expose PATCH /books/{book_id} (see SPEC.md)
