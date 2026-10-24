# Promoz AI Orchestrator

Promoz is an early-stage Python prototype for turning natural-language requests into structured tasks and routing those tasks to configured service endpoints. It uses FastAPI, SQLAlchemy, SQLite by default, and OpenRouter for language-model responses.

> **Project status:** Prototype, not production-ready. External services must be configured separately. The queue is in-memory, API authentication is not implemented, and pending work may not be recovered after a restart. Run it only on a trusted development machine or network; do not expose it directly to the public internet.

## Current capabilities

- Natural-language command parsing through the OpenRouter API.
- Structured task records, priorities, statuses, and conversation-history models.
- FastAPI endpoints for commands, tasks, queue status, conversations, and health.
- Priority-based in-process queue that calls configured task-service endpoints.
- A browser-based dashboard and API documentation.

A task is only as capable as the configured service that receives it. The repository should not be treated as a general-purpose autonomous agent or as a verified integration with every example service listed in the configuration.

## Architecture

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy.
- **LLM integration:** OpenRouter Chat Completions API.
- **Database:** SQLite by default; other SQLAlchemy-supported databases may require configuration and validation.
- **Frontend:** Static HTML/CSS/JavaScript and a separate frontend/web application.
- **Task execution:** In-process priority queue with HTTP requests to configured services.

## Quick start

### Prerequisites

- Python 3.11 or newer.
- An OpenRouter API key for natural-language command parsing.
- Git.

### Install

```bash
git clone https://github.com/saichaitanyarestaurant-ctrl/promoz.git
cd promoz
python -m venv .venv
```

Activate the environment:

- **Windows PowerShell:** `.venv\\Scripts\\Activate.ps1`
- **macOS/Linux:** `source .venv/bin/activate`

Install backend dependencies and create your local environment file:

```bash
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

Copy `.env.example` to `.env` in the repository root, then set `OPENROUTER_API_KEY` to your own key. Never commit a real API key.

Run the backend from its directory:

```bash
cd backend
uvicorn main:app --reload
```

Local endpoints:

- Dashboard (when the static frontend is available): http://localhost:8000/
- API documentation: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- Versioned API root: http://localhost:8000/api/v1/

## Configuration

The main settings are read from environment variables:

| Variable | Purpose |
| --- | --- |
| `OPENROUTER_API_KEY` | API key used to parse natural-language commands |
| `OPENROUTER_MODEL` | Model ID; defaults to the value in the application |
| `DATABASE_URL` | SQLAlchemy database URL; defaults to local SQLite |
| `HOST` / `PORT` | Server bind address and port |
| `CORS_ORIGINS` | Allowed frontend origins |

Keep secrets in `.env` or another secrets manager; `.env.example` contains placeholders only.

## Tests

The unit tests use an isolated in-memory SQLite database and do not require an OpenRouter key or running service endpoints.

From the repository root:

```bash
python -m pip install -r backend/requirements.txt
python -m pytest -q backend/tests
```

GitHub Actions runs the offline unit tests on pushes to the maintenance branch and `main`, and on pull requests targeting `main`.

## API overview

Routes are mounted under `/api/v1`:

- `POST /command` — parse and enqueue a command.
- `GET /task/{task_id}` — retrieve a task.
- `GET /tasks` — list tasks, optionally filtered by status.
- `GET /queue/status` — queue counters.
- `DELETE /task/{task_id}` — cancel a pending task.
- `GET /services/health` — service health summary.
- `POST /conversation` and `GET /conversation/{conversation_id}` — conversation operations.
- `GET /health` — API health check.

Interactive OpenAPI documentation is available at `/docs` when the backend is running.

## Known limitations

- Authentication, authorization, rate limiting, and tenant isolation are not implemented.
- The queue is held in process memory and is not a durable distributed queue.
- External service endpoints and their credentials must be configured and tested independently.
- Production deployment, concurrency behavior, restart recovery, and security boundaries need further validation.
- Automated tests cover core validation and queue behavior; they do not establish that every external integration works end-to-end.

Contributions that improve tests, setup reliability, safe defaults, and the documented behavior are welcome. Please open an issue to discuss substantial changes before submitting a pull request.

## Licence

This project is licensed under the [MIT License](LICENSE).

## Acknowledgements

- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [OpenRouter](https://openrouter.ai/)
- [pytest](https://docs.pytest.org/)
