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
