## Duplicate ISBN handling

Duplicate ISBNs are checked with an explicit SELECT before inserting the book.
This was chosen over catching `IntegrityError` because the application-level
behavior is more readable and obvious: an existing ISBN is rejected with HTTP
409 Conflict.

This SELECT is subject to a TOCTOU (time-of-check/time-of-use) race under
concurrent requests. The database UNIQUE constraint remains the actual
correctness guarantee. The explicit SELECT is primarily responsible for
providing the expected 409 response during the normal duplicate case.