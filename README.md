# Sanctum Sanctorum — Members' Bookstore

A small backend for a members-only clubhouse bookstore. Members can **buy** books and
**borrow** them from the club library. The codebase is only partly finished. Your job is
described in [ASSIGNMENT.md](ASSIGNMENT.md), and how the exercise runs — timeline, grading,
Git, deployment and AI usage — is in [INSTRUCTIONS.md](INSTRUCTIONS.md).

## Quick start

You do **not** need Python, `make`, or anything else installed first. The one tool to install is
[uv](https://docs.astral.sh/uv/getting-started/installation/), which downloads the correct Python
version and all dependencies for you.

### Step 1 — install uv

Pick the line for your system and run it in a terminal:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then **close and reopen your terminal** so the updated `PATH` takes effect, and check it worked:

```
uv --version
```

If that prints a version number, you're set. If it says "command not found" or "not recognised",
reopen the terminal again, or see uv's
[installation guide](https://docs.astral.sh/uv/getting-started/installation/) for other options
(Homebrew, winget, pipx, standalone installers).

### Step 2 — run the project

These commands are **the same on macOS, Linux and Windows**. Run them from the repository root
(the folder containing `pyproject.toml`):

```
uv sync                                  # install Python + dependencies (first time only)
uv run pytest                            # run the test suite
uv run uvicorn app.main:app --reload     # start the app
```

The first `uv sync` takes a minute while it downloads Python; after that everything is instant.

- Web UI: http://localhost:8000
- Interactive API docs (Swagger): http://localhost:8000/docs
- The SQLite database (`sanctum.db`) is created and seeded on first start. To start fresh, stop the
  app and delete that file (`rm sanctum.db`, or `Remove-Item sanctum.db` in PowerShell).

That's the whole setup. The sections below are optional alternatives — you don't need them.

<details>
<summary>Optional: shorter commands with <code>make</code></summary>

If you already have `make` (usually present on Linux; on macOS it comes with the Xcode command line
tools, `xcode-select --install`; on Windows it is not installed by default), there's a `Makefile`
with shortcuts:

```bash
make setup      # uv sync
make test       # uv run pytest
make run        # uv run uvicorn app.main:app --reload
make reset-db   # rm -f sanctum.db
```

These are only shortcuts for the `uv` commands above. If you don't have `make`, ignore this — don't
install it just for this project.
</details>

<details>
<summary>Optional: no uv? Use Python and pip directly (needs Python 3.10+)</summary>

This route needs Python already installed. Check with `python3 --version` (macOS/Linux) or
`py --version` (Windows); if it's missing or older than 3.10, install it from
[python.org/downloads](https://www.python.org/downloads/) — or just use uv above, which handles it
for you.

```bash
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" "sqlalchemy>=2" "pydantic>=2" pytest httpx
pytest
uvicorn app.main:app --reload
```

```powershell
# Windows (PowerShell)
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install fastapi "uvicorn[standard]" "sqlalchemy>=2" "pydantic>=2" pytest httpx
pytest
uvicorn app.main:app --reload
```

On Windows, if PowerShell blocks the activation script, either run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or use `.venv\Scripts\activate.bat`
from `cmd.exe`. Remember to activate the virtual environment in every new terminal.
</details>

## Project layout

```
app/
  main.py        app factory, error handlers, router wiring
  db.py          engine, session, Base, get_db dependency
  clock.py       get_now dependency (always use this for the current time)
  models.py      SQLAlchemy models
  schemas.py     Pydantic request/response models and validation
  seed.py        demo data
  routers/       HTTP layer (thin)
  services/      business logic  <- most of your work is here
frontend/        static UI served at /
tests/           the test suite (your acceptance criteria)
SPEC.md          the full API specification
```

## Running tests

```
uv run pytest                          # everything
uv run pytest tests/test_orders.py     # one file
uv run pytest -k late_fee -x           # by name, stop at first failure
```

(If you set the project up with pip instead of uv, drop the `uv run` prefix and just use `pytest`,
with your virtual environment activated.)

Each test gets a fresh in-memory database and a **frozen clock** (`clock.advance(days=15)`),
so tests are fast and deterministic. Endpoints that haven't been built yet return
`501 Not implemented`.
