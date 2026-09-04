# Copilot instructions

This repository is a Python Telegram bot and FastAPI app for a medical education platform. Follow the project’s established async patterns and keep bot flows stable.

## Priority rules
- Preserve existing registration, admin, and callback flows.
- Use the repo’s `db.*` async API rather than introducing ad hoc DB access.
- Maintain compatibility with `python-telegram-bot` 21.x and async `ApplicationBuilder` patterns.
- Keep Persian-language Telegram messages and HTML formatting intact when editing UI strings.

## Key files
- `bot.py`: main application bootstrap and job registration.
- `start.py`: onboarding and registration handlers.
- `message_router.py`: message dispatch.
- `api/main.py`: FastAPI app entry.
- `db/`: persistence layer.

## Validation
- Prefer the smallest relevant test or smoke check for the changed behavior.
- Run `pytest -q` when a fix affects shared logic or multiple modules.
- For bot changes, verify the relevant handler flow still imports and runs without crashing.

## Change hygiene
- Prefer surgical edits and minimal diffs.
- Do not introduce broad refactors or unrelated cleanup in the same patch.
- Keep secrets and environment configuration out of source control.
