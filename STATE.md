# STATE

## Current step
All build prompts (0–13) implemented in one pass. **Verification status: see "Known issues"** – the build container had no access to PyPI/npm, so the FastAPI/SQLAlchemy/WeasyPrint/React parts are verified only by GitHub Actions CI, not locally.

## Done
- 0 Repo skeleton, AGENTS.md, STATE.md, .gitignore, .env.example, README, Makefile + `scripts/dev.sh`, `/health`.
- 1 SQLAlchemy models + Alembic `0001_initial`; settings service (batch 10, 8.5x11in, en); persistent job runner (progress, retry, cancel, resume after restart); provider interfaces; mock image/text/vision providers; Claude adapter (official `anthropic` SDK, model from env, retries, UsageLog); prompt loader with `{placeholders}` and one JSON repair retry; settings/jobs REST.
- 2 React + TS + Vite shell, router, TanStack Query, react-i18next (en/ar, RTL via logical properties, Cairo font), light/dark tokens, books list, 9-step wizard with sticky step bar and Back/Next bar.
- 3 Source: URL fetcher with SSRF guard, HTML/OG/JSON-LD parsing, preview images, uploads (PNG/JPEG/WEBP/PDF→15 pages), analysis job, confidence rules, originality scrub, source images deleted after analysis, editable recipe.
- 4 Themes (3, regenerate), formats (3–4 + hybrid), shares always 100, page plan with exact type allocation, distinct descriptions, text content for code pages.
- 5 Characters: briefs, 4 candidates, select, lock-and-edit with version history, sheet (3 views + 3 expressions), style anchor, consistency test (3 scenes, vision verdict, override), sample page gate, library save/reuse.
- 6 OpenAI + Gemini image adapters (reference images), comparison harness (CLI + Settings page, scores 1–5, summary table, no winner picked), provider per book or global.
- 7 Generation job: batches, concurrency, programmatic QA → vision QA → auto-redo ×2 with issues appended → failed; cleanup to 300 DPI pure B/W with 0.5in safe margin (+bleed); resumable; cost ceiling pause; per-page regenerate.
- 8 Code-drawn pages: maze (solvable, difficulty), dot-to-dot, word search (EN/AR, answer key data), trace & write, Q&A, story, title, belongs-to, end – HTML → WeasyPrint → PNG.
- 9 Review grid: failed first, tap to reject, redo only rejected with note, approve all, page detail, cached thumbnails.
- 10 Interior PDF (exact trim+bleed, code page numbers, Arabic-Indic digits for Arabic books) and cover PDF (3 templates, live title, chosen page or generated art), cover preview, PDF preview in the UI.
- 11 Google Drive: OAuth installed-app flow (`drive.file`), token 0600, unique folder naming, upload planning, resume/skip existing, quota/expired-token errors.
- 12 Book Brief builder, planning prompt, page prompt packs (5/10), `.md` download, import (JSON or numbered list) with readable errors and diff.
- 13 Cost view (per book / per page / redos), cost ceiling, backup zip export + re-import, README, CI.

## Decisions
- Prompt files live in `backend/app/prompts/` (PLAN §5 layout) rather than `backend/prompts/` (§10), so they ship with the package.
- Added columns beyond PLAN §6: `Book.style_anchor`, `Book.meta` (fetch info, sample, cover, drive, per-book provider), `Page.description`, `Page.meta` (character ids, user note), `Job.message/result/attempts`, `UsageLog.page_id/purpose`. Needed for the style anchor, gates and per-page cost.
- Config is read with a tiny dependency-free loader instead of `pydantic-settings` (fewer deps; pure modules testable without the web stack).
- Page **types and order** are allocated by code from the format shares (largest remainder, evenly spread); the LLM only fills descriptions and text. Guarantees exact shares and page counts.
- Image pages are stored as cleaned 1-bit PNGs; code pages are re-rendered as vector HTML in the interior PDF (crisp text, correct Arabic shaping).
- Trace & write uses light-grey letters on guide lines (reliable Arabic shaping) instead of dotted SVG outlines.
- A “pause” is a cancel + resume: generation only processes `queued` pages, so retrying the job continues where it stopped.
- Default Claude model `claude-opus-5-5` (configurable via `ANTHROPIC_MODEL`).
- Image cost estimates are configurable defaults (`COST_TABLE`), not authoritative prices.

## Dependencies
Backend: fastapi, uvicorn[standard], sqlalchemy 2, alembic, pydantic 2, httpx, python-multipart, pillow, numpy, weasyprint, pypdfium2 (PDF→images, HTML page rasterizing), beautifulsoup4 (store page parsing), anthropic, google-api-python-client, google-auth-oauthlib. Dev: pytest, ruff.
Frontend: react, react-dom, react-router-dom, @tanstack/react-query, i18next, react-i18next. Dev: typescript, vite, @vitejs/plugin-react, vitest, @types/react(-dom).

## Open questions (resolved by the comparison harness, not guessed)
- Which image provider/model for line art and for reference-based consistency.
- Whether batch size 10 works for manual use, else 5.
- Default concurrency and per-book cost ceiling.

## How to run
See README: `make setup && make dev`; tests `make test`; harness `make compare ARGS="--providers mock,openai"`.

## Known issues
- Built in a container without PyPI/npm access: pure-logic backend tests (specs, cleanup, QA, renderers, SSRF/fetcher, prompts, providers, Drive planning, harness) ran locally; DB/API/PDF tests and the frontend type check/build run only in GitHub Actions.
- Fonts are not committed (downloaded by `make fonts`); PDFs fall back to DejaVu Sans / system Noto.
- No end-to-end run against real image/LLM providers has been done yet (needs keys); run the comparison harness first.
- Vision QA and consistency checks depend on the chosen LLM; with mocks they always pass.
- Hosted mode (v2: auth, HTTPS, rate limits) is out of scope.
