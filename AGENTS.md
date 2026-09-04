# AGENTS.md

## Project overview
This repository is a mixed Python Telegram bot + FastAPI service for a medical education platform. The core runtime is centered around the Telegram bot entry in `bot.py`, user registration flows in `start.py`, and the API app in `api/main.py`.

Key architecture notes:
- The Telegram bot uses `python-telegram-bot` 21.x and async handlers.
- Conversation state is managed through `ConversationHandler` for registration flows.
- Many other features are handled by standalone callback/message handlers rather than one giant state machine.
- Database access is async and commonly goes through `db.*` helpers.
- The repo also contains a miniapp frontend and a webadmin frontend.

## Operating principles
- Prefer surgical, minimally invasive changes.
- Preserve existing Telegram callback patterns and message flow semantics.
- Do not break admin or user registration flows without updating the relevant handlers.
- Keep async I/O patterns consistent; avoid synchronous DB calls in async handlers.
- Keep changes compatible with the project's Persian-language UI and HTML-formatted Telegram messages.

## Working commands
- Install dependencies:
  - `pip install -r requirements.txt`
- Run the Telegram bot locally:
  - `python bot.py`
- Run the API server locally:
  - `uvicorn api.main:app --reload`
- Run the test suite:
  - `pytest -q`

## Validation expectations
- Before claiming a fix is complete, run the smallest relevant verification command.
- For behavior changes, prefer a targeted test or a lightweight reproduction/check.
- If no direct test exists, validate by running the relevant module or API entry point and confirming the expected flow.

## Repository guidance
- `start.py` contains registration and onboarding logic; changes here can affect access and approval flows.
- `bot.py` is the main Telegram application bootstrap; be careful with imports, handler registration, and jobs.
- `message_router.py` and `admin.py` are central dispatch points; avoid duplicating logic or conflicting handlers.
- `db/` contains the persistence layer; follow existing naming patterns and return shapes.
- `api/` contains the HTTP API, and `miniapp/` / `webadmin/` are frontend assets that may need feature parity with backend APIs.

## Constraints
- Do not commit or expose secrets or tokens.
- Avoid destructive migrations or mass refactors without clear need.
- Keep compatibility with the existing environment and deployment assumptions.
- Prefer explicit validation of user input and safe error handling in Telegram flows.
