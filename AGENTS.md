# Working rules for coding agents

1. At session start read `PLAN.md` (source of truth) and `STATE.md` (current state).
2. Work on exactly one step (see `BUILD_PROMPTS.md`). Plan first, then build.
3. Small commits with clear messages.
4. Never add a dependency without listing it in `STATE.md` (Dependencies section) and in `backend/pyproject.toml` / `frontend/package.json`.
5. Never commit secrets. Keys live only in `.env` (git-ignored); `.env.example` documents them.
6. Keep provider/model names in configuration, never in code logic.
7. No text inside generated images; all text is rendered by code.
8. All UI strings go in `frontend/src/i18n/en.json` and `ar.json` (same keys). Use CSS logical properties so RTL works.
9. The whole pipeline must keep working with the mock providers offline (`pytest` must pass without API keys).
10. Update `STATE.md` at the end of every session.
11. Stop and ask when the plan is ambiguous or a prompt disagrees with `PLAN.md`.
