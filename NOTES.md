# Sanctum Sanctorum — Notes

**Live:** https://sanctum-sanctorum-main.onrender.com

Render's free tier sleeps after ~15 minutes idle; the first request after a sleep
can take ~50 seconds. It is not down — please retry.

The UI asks you to choose a member to act as before borrowing or ordering. Tier
drives both the order discount and access to restricted books, so the seeded
members cover every case:

| id | name | tier | restricted books |
|---|---|---|---|
| 1 | Wong Li | supreme | yes (15% discount) |
| 2 | Christine Palmer | master | yes (10% discount) |
| 3 | Jonathan Pangborn | adept | no (5% discount) |
| 4 | Sara Lin | apprentice | no (no discount) |

Twelve books are seeded, two of which are restricted (`Darkhold`,
`Principles of Celestial Mechanics`).

---

## What is done

All **202 tests pass** (`uv run pytest`). Every endpoint in SPEC.md is implemented:
books (validation, ISBN checksum, filtering, sorting, pagination, partial updates),
members (validation, duplicates, stats), orders (pricing, discounts, stock
reservation, status changes), loans (borrowing rules, returns, late fees) and the
top-books report.

## What is not done

- **No migration to hosted Postgres.** The deployment runs SQLite on the
  container's local disk. See *Deployment* below for the reasoning and the
  limitation this carries.
- **None of the optional extras.** No concurrency-safe handling of the last copy
  of a book (the trade-off is analysed under *Order stock concurrency*), no
  `GET /members` endpoint with pagination, and no additional tests beyond the
  supplied suite.
- **`create_loan` loads all of a member's loans** to count active ones and check
  for overdue ones, rather than filtering in SQL. Correct and readable at this
  scale; it would need a query-side filter if members accumulated many loans.

---

## Deployment

**Platform: Render.** The app is a long-running ASGI service, so a container host
runs it unchanged — `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Vercel
would have required an ASGI shim and imposed cold starts on a serverless runtime,
for no benefit here. Render was also the option with a genuinely free tier.

**Database: SQLite on the container's local disk.** This disk is ephemeral: a
redeploy or an idle spin-down resets the database. The app tolerates this because
the lifespan handler reseeds an empty database on startup, so the service always
returns to a working demo state rather than a broken one. What is lost is data
created between restarts.

Postgres is the correct choice for real persistence, and I would migrate with more
time. I stayed on SQLite to respect the explicit "don't add new dependencies" rule
in ASSIGNMENT.md — SQLAlchemy cannot speak to Postgres without a DBAPI driver, so
that move is not a configuration change. See *AI usage* for how I reached that
decision.

`app/db.py` needed one fix for this to be a configuration choice rather than a
hardcoded one: `connect_args={"check_same_thread": False}` was passed
unconditionally, but that argument is SQLite-only and would break any other
backend. It is now applied only when the URL is a SQLite URL, so switching
`SANCTUM_DATABASE_URL` is the only change a migration needs on the application
side.

---

## Architectural decisions

### Where validation lives

Value-level rules live in Pydantic schemas; rules that need the database live in
services. This is not only tidiness — it fixes response-code precedence for free.
An order with a duplicated `book_id` and a non-existent member must return 422,
not 404. Because Pydantic runs before the handler, putting the duplicate check in
`OrderCreate` makes that ordering automatic. Implemented in the service, it would
have to be hand-ordered against the 404, which is more code and easier to get
wrong.

### Order creation is two passes

`create_order` validates everything — member, every book, restricted access, stock
for every item — before mutating anything. Only then does it decrement stock and
build the order.

The transaction would roll back a partial failure anyway, but the two-pass shape
makes the all-or-nothing guarantee visible in the structure of the function rather
than leaving it implied by the session lifecycle. A reader can see that no write
happens until every check has passed.

### Duplicate ISBN handling

Duplicate ISBNs are checked with an explicit SELECT before inserting the book.
This was chosen over catching `IntegrityError` because the application-level
behaviour is more readable and obvious: an existing ISBN is rejected with HTTP 409
Conflict.

This SELECT is subject to a TOCTOU (time-of-check/time-of-use) race under
concurrent requests. The database UNIQUE constraint remains the actual correctness
guarantee. The explicit SELECT is responsible for producing the expected 409
response in the normal duplicate case.

### Duplicate member email handling

Member emails are normalized by stripping whitespace and lowercasing before
validation and storage. Duplicate detection therefore uses plain equality against
the normalized email.

No `func.lower()` is used because every stored email is already lowercase. This
also keeps the email index directly usable.

### Order stock concurrency

The validate-then-mutate flow is safe for sequential requests but is not fully
concurrency-safe. Two simultaneous orders can both read the same available stock
before either transaction commits, allowing both to reserve the same copies.

A production implementation should make the stock decrement atomic:

```sql
UPDATE books
SET stock = stock - :q
WHERE id = :id AND stock >= :q
```

and verify that exactly one row was updated, or use `SELECT ... FOR UPDATE` to
lock the book row across validation and mutation.

I left the readable version in place and documented the gap rather than adding
locking that the test suite does not exercise.

### Loan status layering

Sharing the overdue rule between the `loans` and `members` services initially
created a circular import: `members` needed `loan_status`, and `loans` needed
`get_member`. Rather than deferring the import, I treated the cycle as evidence
that the rule belonged in a lower layer.

`loan_status` moved to `Loan.status_at(now)`. Computing a loan's status requires
only the loan's own state and a timestamp — no database, no service — so a service
was never the right home for it. There is precedent in the supplied code:
`OrderItem.line_total_cents` is already a derived value computed on the model.

The timestamp stays an explicit parameter rather than being read from a clock
inside the model. That preserves the `get_now` dependency rule from SPEC.md and
keeps the calculation deterministic and testable.

The alternative was a deferred import inside the service function. I rejected it
because it would hide the dependency cycle instead of correcting the layering.
Service imports now run one way only: `orders` and `loans` depend on `members` and
`books`; nothing depends back on them.

---

## Notes on the spec

**Mixed-case sort ordering.** SPEC.md states that ordering of mixed-case titles is
unspecified, and the tests accept either behaviour. On SQLite, `ORDER BY title`
sorts uppercase before lowercase, so `Zebra` precedes `apple`. Postgres under a
typical locale collation does not. This is worth flagging because it means
`GET /books?sort=title` would return a different order after migrating, without
any application change.

**Loan boundary.** The strictness of the `due_at` boundary is stated in SPEC.md
but is easy to miss, and it appears in three places: loan status, the overdue
check that blocks borrowing, and member stats. Keeping one definition in
`Loan.status_at` was what made this consistent rather than three separate
comparisons.

## Issues found in the provided code

`frontend/app.js` renders a Return button for every unreturned loan
(`data-action="loan-return"`, line 1315) and defines `returnLoan()` (line 1324),
but the click dispatcher's `switch` had no `case 'loan-return'`. The handler was
never invoked, so the button silently did nothing — no request, no error — while
`POST /loans/{id}/return` worked correctly via the API and in the test suite.

I have left this unfixed and `frontend/` unmodified. ASSIGNMENT.md scopes the work
to `app/`, so I treated the supplied frontend as outside the brief rather than
quietly editing it. The fix is one line — `case 'loan-return': returnLoan(id,
target); break;` alongside the existing `borrow` case in the dispatcher, around
line 1402.

Loan returns can be exercised meanwhile through `POST /loans/{id}/return`, either
directly or from the Swagger UI at `/docs`.

## Git history

Late in the process I rewrote three commit messages for accuracy and split one
commit that had bundled four unrelated changes. No history was removed: the commit
count went up, and an early false start on `loan_status` is deliberately retained.

---

## AI usage

I used Antigravity throughout the exercise, mainly as a review and debugging assistant. I ran the tests myself and used it to understand failures, compare implementation approaches, and review decisions rather than treating its suggestions as automatically correct.

What I used it for:

* **Reading the test suite as a specification.** The tests encode rules that are easy to miss in the prose — for example, the id tie-break remaining ascending when sorting `-title`, and the strict `due_at` boundary. I used Antigravity to cross-reference `SPEC.md` with `tests/`, then checked those findings against the test files myself.

* **Finding unmarked defects.** Several issues had no `TODO`: `tier_at_least` used `>` instead of `>=`, `list_books` calculated `total` from the paginated results rather than the full match set, and `cancel_order` did not restore stock despite its own docstring saying it should. Using the tests and documentation as cross-checks helped surface these quickly.

* **Reviewing architecture.** I used it as a second opinion on validation placement, transaction structure, and the dependency problem between the loans and members services.

* **Review after each phase.** I ran the test suite myself and used Antigravity to explain specific failures and suggest possible fixes. I then implemented and verified the changes.

### Where I overrode it

At the deployment step, Antigravity recommended adding `psycopg[binary]` for PostgreSQL and treating the dependency restriction as an exception. I did not accept this because `ASSIGNMENT.md` explicitly says not to add new dependencies.

I deployed with SQLite instead. The database is on Render's ephemeral container disk, and the lifespan handler reseeds an empty database on startup. This makes the deployment suitable for the take-home demo, although it would not be an appropriate persistence strategy for a production service. I documented that limitation rather than relaxing the dependency constraint.

The SQLite-specific part of the suggestion was still useful: `app/db.py` was passing `check_same_thread=False` unconditionally. I kept the fix but made it conditional on the database URL being SQLite, so the database configuration is not tied to SQLite.

Later, Antigravity initially suggested moving the shared `loan_status` function into a separate utility module after a circular import appeared between the loans and members services. I did not use that approach.

Instead, I treated the circular import as a sign that the rule belonged in the model layer and moved it to `Loan.status_at(now)`. The rule only depends on the loan state and an explicitly supplied timestamp, so it does not need a service or database. Passing `now` explicitly also preserves the `get_now` dependency rule and keeps the calculation deterministic and testable.

I also considered the alternative of using a deferred import inside the service, but rejected it because that would hide the dependency cycle rather than fix the underlying layering problem.

The final implementation reflects the decisions I made after reviewing the suggestions and verifying the behavior against the supplied tests.

I also used Antigravity to review and improve the documentation in NOTES.md, while keeping the final explanations and decisions aligned with the implementation I actually submitted.