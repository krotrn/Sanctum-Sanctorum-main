"""Reporting queries."""
from typing import List

from sqlalchemy.orm import Session

from app.schemas import TopBook


def top_books(db: Session, limit: int = 5) -> List[TopBook]:
    """Best-selling books.

    Rules: copies_sold sums quantities over ``paid`` orders only; books with no sales are
    excluded; sorted by copies_sold desc, then title asc; at most ``limit`` rows.
    """
    raise NotImplementedError("top_books")
