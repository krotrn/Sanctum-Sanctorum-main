# How this assignment works

Read this first. [ASSIGNMENT.md](ASSIGNMENT.md) says *what* to build, [SPEC.md](SPEC.md) is the
detailed API contract, and this file explains *how* the exercise runs: the timeline, how we grade,
and what we expect around Git, deployment and AI tools.

---

## 1. Timeline

**You have 1 week** from the day you receive this repository.

It should not take a week of full-time work. We expect somewhere around **8–15 hours** total, spread
across the week so you can think between sessions. The extra calendar time is deliberate: we would
rather see considered decisions than a rushed sprint.

The deadline is the deadline, so plan the week accordingly. If something serious comes up, tell us
as soon as you know rather than going quiet.

---

## 2. What we are actually assessing

The test suite is the floor, not the ceiling. Passing tests shows you can read a spec and write
correct logic. The rest of the score is about **how** you got there.

| Area | Weight | What we look for |
|---|---|---|
| **Architecture & design decisions** | 30% | Sensible boundaries between layers; logic in services rather than smeared into routers; models that reflect the domain; choices you can defend, and trade-offs you noticed |
| **Code quality** | 25% | Readable, consistent code that matches the style already in the repo; good naming; small focused functions; no copy-paste; no dead code or debug leftovers |
| **Correctness** | 15% | Passing tests, plus edge cases and data integrity (a failed order must never leave stock half-updated) |
| **Deployment** | 10% | A working, reachable deployment of your app, and the reasoning behind the platform and database choices you made |
| **Git history & process** | 10% | Incremental, meaningful commits that tell the story of your work (see below) |
| **Communication** | 10% | Your `NOTES.md`: what you did, what you skipped, what you would do with more time |

A clean, well-reasoned 80% beats a messy 100%. We would rather see four features done well and an
honest note about the fifth than five features held together with tape.

---

## 3. Git is part of the submission

**Use Git properly and keep your full history.** We read it.

- Commit incrementally as you work. Roughly one commit per logical change.
- Write real commit messages: `Add ISBN-13 checksum validation` beats `fix`, `wip` or `changes`.
- **Do not squash everything into one commit** at the end, and do not delete and re-create the
  repository to hide false starts. A history showing you explored, backtracked and refactored is a
  *positive* signal — it shows how you think.
- Branches and pull requests are welcome if that is how you like to work, but not required.
- Do not commit `.venv/`, `sanctum.db`, `__pycache__/` or secrets. The `.gitignore` covers these.

Keep the existing commit as the first commit of your history, so the diff of your work is clear.

---

## 4. Deployment (required)

**You must deploy your app and give us a working public URL.** Shipping something is a different
skill from making tests pass, and it is one we care about. A submission with no live URL is
incomplete.

Deploy whatever you have, even if some features are unfinished — a deployed partial implementation
is worth far more to us than a perfect one that only runs on your laptop. Deploy early rather than
leaving it to the last evening; it always takes longer than expected the first time.

Suggested stack, all with free tiers:

- **[Supabase](https://supabase.com)** — hosted Postgres for the database
- **[Vercel](https://vercel.com)** — hosting for the frontend, and the API if you make it work there

Equivalents are completely fine, and some are a smoother fit for a Python API:
**Render**, **Railway**, **Fly.io**, **Deta**, **PythonAnywhere** for the backend, and
**Neon** or **Railway Postgres** for the database.

Things you will run into, which are exactly the interesting parts:

- The app ships with **SQLite**. Moving to Postgres means changing `SANCTUM_DATABASE_URL` and
  thinking about what else the switch affects — SQLAlchemy hides most of it, but not all.
- **Serverless platforms have no persistent local disk**, so a SQLite file will silently vanish or
  reset between invocations. That is the main reason to move to a hosted database.
- Running FastAPI on Vercel needs a small ASGI entry point; a container-style host like Render or
  Railway is often less fiddly. Either choice is fine — just explain why you picked it.

**Hard rule:** the test suite must still pass locally with the default SQLite setup and no external
services (`uv run pytest`, or plain `pytest` if you set the project up with pip). Do not make the
tests depend on a live database.

Put the live URL at the top of your `NOTES.md`, and note anything we need in order to use it (for
example a seeded member id to sign in with). We will open it and click around, so make sure it is
actually reachable from outside your machine before you submit.

---

## 5. Using AI tools

**AI assistants are allowed and encouraged.** Copilot, Claude, Gemini, ChatGPT, Cursor — use what
helps. We use these tools daily; pretending otherwise would be silly.

Two conditions:

1. **You must understand and be able to defend every line you submit.** In the follow-up discussion
   we will pick parts of your code and ask why it works that way, what happens in a specific edge
   case, and what you would change. "The AI wrote it" is the one answer that scores zero. Code you
   cannot explain is worse than code you did not write.
2. **Tell us how you used it.** Add a short `## AI usage` section to your `NOTES.md`: which tools,
   what for (scaffolding, debugging, tests, rubber-ducking), and one place where the AI was wrong or
   unhelpful and you had to override it. That last part tells us more about you than the rest.

Good use of AI is a signal in your favour: it shows you can direct a tool, review its output
critically and move faster. Uncritically pasting whatever it produced shows up immediately, usually
as inconsistent style and logic that does not quite match the spec.

### Free and discounted access for students

If you are a student, you likely qualify for paid tiers at no cost. **These offers change often and
vary by country — check the current terms yourself before relying on them:**

- **[Google AI for students](https://gemini.google/students/)** — Google has been offering eligible
  students 12 months of Google AI Plus free in India and 140+ markets, with AI Pro discounted or free
  depending on region, for students at accredited institutions. Verification is through Google One.
- **[OpenAI ChatGPT student offer](https://help.openai.com/en/articles/20001493-chatgpt-back-to-school-offer-for-students)** —
  a Back to School promotion has offered several free months of ChatGPT Plus, verified via SheerID.
  It has been limited to US institutions and runs on a deadline, so check whether it is still open.
- **[GitHub Student Developer Pack](https://education.github.com/pack)** — free Copilot access for
  verified students, bundled with a long list of other developer tools.

The free tiers of Gemini, ChatGPT and Claude are perfectly sufficient for this assignment. Do not
spend money on it.

---

## 6. Submitting

Send us, before your deadline:

1. A link to a **public** GitHub repository containing your work, with its Git history intact.
   Please don't send private repos or zip files — collaborator invites and attachments slow the
   review down. Public is fine for this exercise: it's a practice project from a starter kit, not
   proprietary code. Just make sure you have committed no secrets, API keys or `.env` files.
2. Your `NOTES.md`, covering:
   - The live URL of your deployed app, plus anything we need to use it
   - What you finished and what you did not
   - Architectural decisions and trade-offs you made
   - Anything in the spec you found unclear or think is wrong
   - Your `## AI usage` section
3. Anything else you want us to look at.

### Before you send

- [ ] The test suite runs (`uv run pytest`) and you know exactly which tests pass and which do not
- [ ] The app starts (`uv run uvicorn app.main:app`) and the UI at `/` works
- [ ] Your deployment is live, and you have opened the URL yourself in a fresh browser window
- [ ] The repository is public and you have opened the link in a logged-out browser to confirm it
- [ ] No secrets, `.venv/` or database files committed
- [ ] Git history is intact and readable
- [ ] `NOTES.md` is written

---

## 7. Asking questions

If the spec is ambiguous, you have two valid options: **ask us**, or **make a reasonable decision,
document it in `NOTES.md` and move on**. Both are fine. Being blocked in silence for two days is not.

Questions do not count against you. Nobody has ever lost points for asking.

Good luck. We are looking forward to seeing how you think.
