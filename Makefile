.PHONY: setup run test reset-db

setup:  ## Install dependencies into .venv (installs Python automatically if needed)
	uv sync

run:  ## Start the API + frontend at http://localhost:8000
	uv run uvicorn app.main:app --reload --port 8000

test:  ## Run the test suite
	uv run pytest

reset-db:  ## Delete the local SQLite database (it is re-seeded on next start)
	rm -f sanctum.db
