"""Demo data loaded into an empty database on startup."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, Member, MemberTier

SEED_BOOKS = [
    {"title": "The Book of Vishanti", "author": "Unknown", "isbn": "9780192834010", "price_cents": 4999, "stock": 3, "restricted": False},
    {"title": "Codex Imperium", "author": "Unknown", "isbn": "9780140449143", "price_cents": 3999, "stock": 4, "restricted": False},
    {"title": "Darkhold", "author": "Unknown", "isbn": "9780679724773", "price_cents": 9999, "stock": 1, "restricted": True},
    {"title": "A Short History of the Ancient World", "author": "Helen Marsh", "isbn": "9781851685554", "price_cents": 2499, "stock": 8, "restricted": False},
    {"title": "Meditations on First Principles", "author": "Adrian Cole", "isbn": "9780312451028", "price_cents": 1599, "stock": 12, "restricted": False},
    {"title": "Maps of the Night Sky", "author": "Priya Raman", "isbn": "9781590178836", "price_cents": 2999, "stock": 6, "restricted": False},
    {"title": "The Silk Road: Trade and Empire", "author": "Tomas Ruiz", "isbn": "9780007423132", "price_cents": 2199, "stock": 5, "restricted": False},
    {"title": "An Introduction to Stoic Thought", "author": "Margaret Hale", "isbn": "9780393316049", "price_cents": 1299, "stock": 10, "restricted": False},
    {"title": "Comets, Eclipses and Other Omens", "author": "Kenji Watanabe", "isbn": "9780812971361", "price_cents": 1899, "stock": 7, "restricted": False},
    {"title": "Libraries of the Medieval World", "author": "Oliver Grant", "isbn": "9780521472166", "price_cents": 3499, "stock": 2, "restricted": False},
    {"title": "Principles of Celestial Mechanics", "author": "Sofia Lindqvist", "isbn": "9781400083312", "price_cents": 5499, "stock": 3, "restricted": True},
    {"title": "The Philosophy of Time", "author": "Daniel Okafor", "isbn": "9780691156729", "price_cents": 1999, "stock": 9, "restricted": False},
]

SEED_MEMBERS = [
    {"name": "Wong Li", "email": "wong@example.com", "tier": MemberTier.SUPREME},
    {"name": "Christine Palmer", "email": "christine@example.com", "tier": MemberTier.MASTER},
    {"name": "Jonathan Pangborn", "email": "jonathan@example.com", "tier": MemberTier.ADEPT},
    {"name": "Sara Lin", "email": "sara@example.com", "tier": MemberTier.APPRENTICE},
]


def seed_if_empty(db: Session, now: datetime) -> bool:
    """Insert demo books and members when the database has neither. Returns True if seeded."""
    has_data = db.scalar(select(Book.id).limit(1)) is not None or db.scalar(select(Member.id).limit(1)) is not None
    if has_data:
        return False

    db.add_all(Book(**book) for book in SEED_BOOKS)
    db.add_all(
        Member(name=m["name"], email=m["email"], tier=m["tier"].value, created_at=now) for m in SEED_MEMBERS
    )
    db.commit()
    return True
