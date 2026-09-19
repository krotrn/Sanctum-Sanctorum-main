"""ORM models.  Importing this module registers every table on ``Base.metadata``."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import List

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MemberTier(str, enum.Enum):
    """Membership tiers, declared from lowest to highest."""

    APPRENTICE = "apprentice"
    ADEPT = "adept"
    MASTER = "master"
    SUPREME = "supreme"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(200))
    isbn: Mapped[str] = mapped_column(String(13), unique=True, index=True)
    price_cents: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer)
    restricted: Mapped[bool] = mapped_column(Boolean, default=False)


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    tier: Mapped[str] = mapped_column(String(20), default=MemberTier.APPRENTICE.value)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    orders: Mapped[List[Order]] = relationship(back_populates="member", order_by="Order.id")
    loans: Mapped[List[Loan]] = relationship(back_populates="member", order_by="Loan.id")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.PENDING.value)
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    discount_percent: Mapped[int] = mapped_column(Integer)
    discount_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    member: Mapped[Member] = relationship(back_populates="orders")
    # Items keep the order in which they were submitted (insertion order == id order).
    items: Mapped[List[OrderItem]] = relationship(
        back_populates="order", order_by="OrderItem.id", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    # Price snapshot taken when the order was placed.
    unit_price_cents: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")
    book: Mapped[Book] = relationship()

    @property
    def line_total_cents(self) -> int:
        return self.unit_price_cents * self.quantity


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    borrowed_at: Mapped[datetime] = mapped_column(DateTime)
    # TODO: the loan model is incomplete. Still missing (see SPEC.md, "Loans"):
    #   - due_at: when the book must be back (borrowed_at + 14 days)
    #   - returned_at: nullable, set when the book is returned
    #   - late_fee_cents: charged on return, defaults to 0

    member: Mapped[Member] = relationship(back_populates="loans")
    book: Mapped[Book] = relationship()
