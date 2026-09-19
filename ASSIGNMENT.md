# Backend Intern Take-Home: Sanctum Sanctorum Bookstore

## Scenario

You are joining the team that runs the Sanctum Sanctorum members' bookstore. The previous
developer left partway through. Some features work, some are half built, a few have bugs,
and some were never started. The product requirements are written down in
[SPEC.md](SPEC.md), and the test suite in `tests/` encodes them.

## Your task

Make the test suite pass by completing and fixing the application code in `app/`.

```
uv sync        # installs Python and dependencies for you
uv run pytest  # many tests fail at first; that's expected
```

The same two commands work on macOS, Linux and Windows. You only need `uv` installed — see
[README.md](README.md) for how to get it, and for a pip-based alternative.

### Ground rules

- **Do not modify anything in `tests/`.** The tests are the acceptance criteria. If you think a test is
  wrong, say so in your notes (see below) instead of changing it.
- You may change anything in `app/`: models, schemas, services, routers.
- Follow SPEC.md. When the spec and your intuition disagree, the spec wins.
- Use the `get_now` dependency for the current time, never `datetime.now()`. The tests depend on it.
- Don't add new dependencies.

### Suggested order

You can work in any order, but this one builds up gradually:

1. **Books:** validation, duplicates, listing (filters, sorting, pagination), updates
2. **Members:** validation, duplicates, access rules
3. **Orders:** pricing, discounts, stock reservation, status changes
4. **Loans:** the model is incomplete; borrowing rules, returns, late fees
5. **Member stats and reports**

## What we look at

Grading is weighted towards **architectural decisions** and **code quality**, not just the number of
passing tests. The full rubric, the timeline, and our expectations around Git history, deployment and
AI usage are in **[INSTRUCTIONS.md](INSTRUCTIONS.md) — read it before you start.**

In short: keep the layering clean (routers thin, business rules in services), protect data integrity
(a failed order must not leave stock partly changed), commit incrementally with real messages, and
write a `NOTES.md` explaining your decisions.

Partial submissions are welcome. A clean, well-explained 80% beats a messy 100%.

## Time and submitting

**You have 1 week.** We expect roughly 8–15 hours of actual work, not a week of full-time effort.

**Deploying your app to a public URL is required** — see [INSTRUCTIONS.md](INSTRUCTIONS.md) for the
recommended stack, along with the rest of the submission checklist, keeping your Git history intact,
and how to document your AI usage.

## Optional extras

Only if you have time; none of these are required:
- Add tests for any edge case you think is missing
- Handle concurrent orders for the last copy of a book safely
- A `GET /members` endpoint with pagination
