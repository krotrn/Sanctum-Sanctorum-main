"""Order operations: placing, paying and cancelling purchases."""
from datetime import datetime
from typing import Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Book, Member, MemberTier, Order, OrderItem, OrderStatus
from app.schemas import OrderCreate
from app.services.members import ensure_can_access_restricted, get_member
from app.services.books import get_book

# Percentage discount granted by each membership tier.
TIER_DISCOUNT_PERCENT: Dict[str, int] = {
    MemberTier.APPRENTICE.value: 0,
    MemberTier.ADEPT.value: 5,
    MemberTier.MASTER.value: 10,
    MemberTier.SUPREME.value: 15,
}

# Extra discount when the total quantity across all items reaches the threshold.
BULK_QUANTITY_THRESHOLD = 10
BULK_DISCOUNT_PERCENT = 5


def calculate_discount_percent(member: Member, total_quantity: int) -> int:
    """Tier discount, plus the bulk discount when total quantity >= threshold."""
    tier_discount = TIER_DISCOUNT_PERCENT[member.tier]
    bulk_discount = BULK_DISCOUNT_PERCENT if total_quantity >= BULK_QUANTITY_THRESHOLD else 0
    return tier_discount + bulk_discount


def create_order(db: Session, data: OrderCreate, now: datetime) -> Order:
    """Place a pending order and reserve stock.

    Checks, in order (422 for empty items / bad quantity / duplicate books is done by the schema):
    1. 404 member not found; 404 any book not found
    2. 403 any book restricted and member tier below master
    3. 409 any book has insufficient stock (all-or-nothing: nothing is changed)
    Then stock is decremented for every item and prices are snapshotted.
    Pricing: discount_cents = subtotal * percent // 100; total = subtotal - discount.
    """
    member = get_member(db, data.member_id)
    books: Dict[int, Book] = {}

    for item in data.items:
        book = get_book(db, item.book_id)
        books[item.book_id] = book

    if any(book.restricted for book in books.values()):
        ensure_can_access_restricted(member)

    for item in data.items:
        book = books[item.book_id]
        if book.stock < item.quantity:
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient stock for book {book.id} ({book.title})",
            )

    order = Order(
        member_id=member.id,
        status=OrderStatus.PENDING.value,
        created_at=now,
    )
    subtotal = 0
    total_quantity = 0

    for item in data.items:
        book = books[item.book_id]
        unit_price_cents = book.price_cents
        line_total_cents = unit_price_cents * item.quantity
        book.stock -= item.quantity

        order.items.append(
            OrderItem(
                book_id=book.id,
                unit_price_cents=unit_price_cents,
                quantity=item.quantity,
            )
        )
        subtotal += line_total_cents
        total_quantity += item.quantity

    discount_percent = calculate_discount_percent(member, total_quantity)
    discount_cents = subtotal * discount_percent // 100

    order.subtotal_cents = subtotal
    order.discount_percent = discount_percent
    order.discount_cents = discount_cents
    order.total_cents = subtotal - discount_cents

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def get_order(db: Session, order_id: int) -> Order:
    """Return an order by id, or raise 404."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def pay_order(db: Session, order_id: int) -> Order:
    """Mark a pending order as paid. 404 if missing; 409 if not pending."""
    order = get_order(db, order_id)
    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"Cannot pay an order that is {order.status}")
    order.status = OrderStatus.PAID.value
    db.commit()
    db.refresh(order)
    return order


def cancel_order(db: Session, order_id: int) -> Order:
    """Cancel a pending order and restore the reserved stock. 404 if missing; 409 if not pending."""
    order = get_order(db, order_id)
    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"Cannot cancel an order that is {order.status}")
    for item in order.items:
        item.book.stock += item.quantity
    order.status = OrderStatus.CANCELLED.value
    db.commit()
    db.refresh(order)
    return order
