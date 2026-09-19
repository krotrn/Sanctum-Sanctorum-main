# Sanctum Sanctorum Bookstore — API Specification (source of truth)

A members-only clubhouse bookstore. Members can **buy** books (orders) and **borrow**
books from the club library (loans). Tone: professional; the store name and a few seed
book titles are the only themed elements.

Stack: Python 3.10+, FastAPI, SQLAlchemy 2.x (sync, `Mapped[]` style), Pydantic v2, SQLite.
No extra dependencies beyond `pyproject.toml`.

## Fixed contracts (keep these — the tests and the frontend rely on them)
- `app/main.py` exposes `create_app(init_db: bool = True) -> FastAPI` and module-level `app = create_app()`.
  When `init_db` is True, a lifespan handler creates tables on the default engine and seeds demo data if the DB is empty.
  When False it touches no database. It also serves `frontend/` at `/` (StaticFiles, html=True) mounted **after** API routers.
  API routes are at the root (no `/api` prefix). CORS allow all.
- `app/db.py`: `Base`, `engine`, `SessionLocal`, `get_db` (already written).
- `app/clock.py`: `get_now()` returns naive UTC datetime (already written). All business logic that needs "now" MUST get it via `Depends(get_now)`.
- `app/models.py`: all ORM models (importing it registers tables).
- `tests/conftest.py`: already written; fixtures `client`, `clock` (`clock.current`, `clock.advance(days=..)`), `make_book(**overrides)`, `make_member(**overrides)`. Start time `2026-01-01T12:00:00`.
- Datetimes serialize as naive ISO-8601 (`2026-01-15T12:00:00`).
- Errors: `HTTPException` → `{"detail": "..."}`. Validation errors → 422 (FastAPI default).
- A global exception handler maps `NotImplementedError` → **501** `{"detail": "Not implemented: <message>"}`.
- Money is always integer cents.

## Layout
```
app/main.py, db.py, clock.py, models.py, schemas.py, seed.py
app/routers/{books,members,orders,loans,reports}.py   # thin: parse, call service, return
app/services/{books,members,orders,loans,reports}.py  # all business logic lives here
frontend/index.html, styles.css, app.js
tests/...
```
Services raise `HTTPException` (or small custom exceptions mapped in main) for 404/403/409.

## Health
`GET /health` → 200 `{"status": "ok"}`

## Books
BookOut: `{id, title, author, isbn, price_cents, stock, restricted}`

`POST /books` body `{title, author, isbn, price_cents, stock, restricted=false}` → 201 BookOut
- title, author: stripped, then 1–200 chars. Length is measured **after** stripping, so a 206-character
  value that strips down to 200 characters is valid → else 422
- price_cents ≥ 0, stock ≥ 0 → else 422
- isbn: remove hyphens and spaces; result must be 13 digits with a valid ISBN-13 checksum
  (weights 1,3,1,3…; check digit = (10 − sum%10) % 10) → else 422. Stored/returned normalized (digits only).
- isbn already exists (after normalization) → 409

`GET /books/{id}` → 200 BookOut | 404

`PATCH /books/{id}` body any subset of `{title, author, price_cents, stock, restricted}` → 200 BookOut | 404 | 422 (same rules).
Fields not provided are unchanged. `isbn` is not patchable: if sent it is *silently ignored*, not rejected.
Unknown fields are ignored too.

`GET /books` query:
- `q`: case-insensitive substring match against title OR author
- `restricted`: bool filter
- `min_price`, `max_price`: inclusive on price_cents
- `sort`: one of `title`, `-title`, `price`, `-price`; ties broken by id ascending. Omit it for the default
  id-ascending order. Any other value — **including `id`** — is 422
- `limit`: default 20, 1..100 else 422; `offset`: default 0, ≥0 else 422
- Ordering of mixed-case titles is **unspecified**: databases disagree (SQLite sorts uppercase before
  lowercase by default, Postgres usually does not). Either behaviour is accepted.
- Response 200 `{items: [BookOut], total, limit, offset}` where `total` = count matching filters before pagination.

## Members
Tiers (ordered): `apprentice` < `adept` < `master` < `supreme`.

MemberOut: `{id, name, email, tier, created_at}`

`POST /members` body `{name, email, tier="apprentice"}` → 201
- name: stripped, then 1–100 chars (length measured after stripping) → else 422
- email: stripped + lowercased; must match `^[^@\s]+@[^@\s]+\.[^@\s]+$` → else 422
- unknown tier → 422
- email already used (case-insensitive) → 409
- created_at = now (from clock)

`GET /members/{id}` → 200 | 404

`GET /members/{id}/orders` → 200 `[OrderOut]` ordered by id asc | 404 if member missing

`GET /members/{id}/stats` → 200 | 404
```
{member_id, orders_paid, total_spent_cents, active_loans, overdue_loans, late_fees_cents}
```
- orders_paid / total_spent_cents: over orders with status `paid` only (sum of total_cents)
- active_loans: loans not returned (includes overdue ones)
- overdue_loans: not returned and now > due_at
- late_fees_cents: sum of late_fee_cents over returned loans

## Orders
OrderOut:
```
{id, member_id, status, items: [{book_id, quantity, unit_price_cents, line_total_cents}],
 subtotal_cents, discount_percent, discount_cents, total_cents, created_at}
```
Response objects carry exactly these fields and no others (an order item does not expose its own row id).
items ordered as submitted.

`POST /orders` body `{member_id, items: [{book_id, quantity}]}` → 201, status `pending`.
Checks in this order:
1. 422: items empty, any quantity < 1, or the same book_id appears twice
2. 404: member not found; 404: any book not found
3. 403: any book is `restricted` and member tier is below `master`
4. 409: any book has stock < requested quantity. **All-or-nothing**: on failure no stock changes, no order created.
5. Success: decrement stock for every item (stock is reserved at creation).

Pricing:
- unit_price_cents = book price at order time (later price changes don't affect the order); line_total = unit × qty
- subtotal = sum of line totals
- discount_percent = tier percent (apprentice 0, adept 5, master 10, supreme 15) + 5 if total quantity across items ≥ 10
- discount_cents = subtotal × discount_percent // 100 (floor); total = subtotal − discount

`GET /orders/{id}` → 200 | 404

`POST /orders/{id}/pay` → pending → `paid`, 200 OrderOut; any other status → 409; 404.
Stock is unchanged — it was already reserved when the order was created.

`POST /orders/{id}/cancel` → pending → `cancelled`, restores stock of every item, 200 OrderOut; any other status → 409; 404

## Loans
LoanOut: `{id, member_id, book_id, borrowed_at, due_at, returned_at, late_fee_cents, status}`
- status computed at read time: `returned` if returned_at set; else `overdue` if now > due_at; else `active`.
- The boundary is strict: at exactly `due_at` a loan is still `active`, is not overdue anywhere
  (including in member stats), and owes no late fee.

Tier loan limits (concurrent unreturned loans): apprentice 1, adept 3, master 5, supreme unlimited.

`POST /loans` body `{member_id, book_id}` → 201. Checks in order:
1. 404 member not found; 404 book not found
2. 403 book restricted and tier below master
3. 409 member has any overdue loan
4. 409 member already has an unreturned loan of this same book
5. 409 member at tier loan limit
6. 409 book stock == 0
Success: borrowed_at = now, due_at = now + 14 days, returned_at null, late_fee_cents 0, stock −1.

`GET /loans/{id}` → 200 | 404

`POST /loans/{id}/return` → 200 LoanOut | 404 | 409 if already returned
- returned_at = now; stock +1
- if now > due_at: days_late = ceil((now − due_at) / 1 day) (any partial day counts as a full day);
  late_fee_cents = min(days_late × 25, book.price_cents), using the book's price at the time of return.
  Otherwise 0.

`GET /members/{id}/loans?status=active|overdue|returned` → 200 `[LoanOut]` ordered by id asc, optional status filter (computed status), invalid status → 422, 404 member missing.

## Reports
`GET /reports/top-books?limit=5` (1..50 else 422) → 200
`[{book_id, title, copies_sold}]` — `title` is the book's current title; copies = sum of quantities across
**paid** orders only; books with 0 excluded;
sorted copies_sold desc, then title asc (mixed-case tie-breaks are unspecified, as above).
