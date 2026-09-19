## Duplicate ISBN handling

Duplicate ISBNs are checked with an explicit SELECT before inserting the book.
This was chosen over catching `IntegrityError` because the application-level
behavior is more readable and obvious: an existing ISBN is rejected with HTTP
409 Conflict.

This SELECT is subject to a TOCTOU (time-of-check/time-of-use) race under
concurrent requests. The database UNIQUE constraint remains the actual
correctness guarantee. The explicit SELECT is primarily responsible for
providing the expected 409 response during the normal duplicate case.

## Duplicate member email handling

Member emails are normalized by stripping whitespace and lowercasing before
validation and storage. Duplicate detection therefore uses plain equality
against the normalized email.

No `func.lower()` is used because every stored email is already lowercase.
This also keeps the email index directly usable.

An explicit SELECT is used to return HTTP 409 for the normal duplicate case.
The database uniqueness constraint remains the final guarantee under concurrent
requests.


## Order stock concurrency

The current validate-then-mutate flow is safe for normal sequential requests, but it is not fully concurrency-safe. Two simultaneous orders can both read the same available stock before either transaction commits, allowing both to reserve the same copies.

A production implementation should make the stock decrement atomic, for example:

```sql
UPDATE books
SET stock = stock - :q
WHERE id = :id AND stock >= :q
```

and verify that exactly one row was updated, or use `SELECT ... FOR UPDATE` to lock the book row during validation and mutation.

The current implementation prioritises readable all-or-nothing semantics — validation completes before any mutation, so the integrity guarantee is visible in the structure of the function rather than implied by the transaction.


### Loan status layering

Sharing the overdue rule between the `loans` and `members` services initially created a circular import. Rather than deferring the import, I treated the cycle as evidence that the rule belonged in a lower layer.

`loan_status` was moved to `Loan.status_at(now)`, because computing a loan's status requires only the loan state and an explicit timestamp; it does not require a database or service.

The timestamp remains an explicit parameter rather than being read from a clock inside the model. This preserves the `get_now` dependency rule and keeps status calculations deterministic and testable.

An alternative was a deferred import inside the service function. I rejected that approach because it would hide the dependency cycle instead of correcting the layering.

**Decision:** Keep `Loan.status_at(now)` as the single definition of loan status and let both `loans` and `members` use it.

## AI usage

I used Antigravity throughout this exercise. Concretely, I used it for:

* **Review after each fix.** I ran the test suite myself and used Antigravity to explain specific failures rather than to write the fixes.

### Where I overrode it

Antigravity recommended adding `psycopg[binary]` for PostgreSQL deployment, but I did not accept this because `ASSIGNMENT.md` explicitly prohibits new dependencies.

I deployed with SQLite instead. The app reseeds an empty database on startup, so this is acceptable for the take-home demo, though it would not be appropriate for a real production service. I documented the limitation rather than overriding the dependency constraint.

I separately fixed `app/db.py` so the SQLite-only `check_same_thread` option is applied only when using SQLite.

Antigravity initially suggested moving the shared `loan_status` function into a separate utility module after a circular import appeared between the `loans` and `members` services. I did not use that approach.

Instead, I treated the circular import as a layering signal and moved the rule to `Loan.status_at(now)` in `app/models.py`. Loan status depends only on the loan state and an explicitly supplied timestamp, so it does not require a service or database. Keeping `now` as a parameter also preserves the `get_now` dependency rule and keeps the calculation deterministic and testable.

I considered the alternative of using a deferred import inside the service, but rejected it because that would hide the dependency cycle rather than correct the layering.
