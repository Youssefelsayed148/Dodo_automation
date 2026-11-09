# STATE

## Current step
Manual mode (ChatGPT Pro, no paid API) implemented per `MANUAL_MODE_PLAN.md` (work order 1–7). Before that: all build prompts (0–13) implemented in one pass. Full CI is green (GitHub Actions run #3): backend ruff + full pytest suite (DB, API, generation, PDFs, Arabic) + harness smoke test on the mock provider; frontend vitest + type check + build.

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

## Manual mode (MANUAL_MODE_PLAN.md) – done
- `ManualTask` model + Alembic `0002_manual_tasks`; job status `waiting` (runner: `AwaitingManual` → waiting, `resume_if_ready` re-queues when no task is pending; waiting jobs are active for dedupe/cancel and ignored by `claim_next`; contextvar `current_job`).
- `services/manual.py`: mode switch (setting `manual_mode` → `MANUAL_MODE` env → auto), `request_text`, `image_batch` (API mode calls the provider; manual mode returns answers or creates all missing tasks at once), `submit_text` (JSON extraction, Pydantic model named in the task, `expected_count`, readable errors + fix prompt), `submit_image`, `bulk_images` (filename number → label, else in order), `skip` (`min_done` per group), task grouping + one-message "copy all prompts".
- `providers/manual.ManualTextLLM` (text + vision) chosen by the registry in manual mode (test overrides still win); `llm.structured()` passes model name/meta and skips the repair round trip in manual mode.
- Steps: analysis (source pictures kept as task references until answered), themes/formats/briefs (1 text task each), candidates (batch of 4, skippable, min 1), lock-and-edit (template, no LLM), sheet (one combined image, `view: combined`), consistency (3 skippable scenes, user verdicts), sample, page plan (prompt per image page, count enforced), generation (code pages first, image pages one batch at a time, programmatic QA only, failures shown in Review), review redo (new tasks with note + issues), cover art (skippable), content QA skipped.
- API: `GET /api/books/{id}/manual`, `POST /api/manual/{task}/text|image|skip`, `GET /api/manual/{task}/ref/{n}`, `POST /api/books/{id}/manual/images`, `POST …/characters/{cid}/consistency/verdict`, `GET /api/books/{id}/chatgpt-setup`, settings `manual_mode` + `manual` info.
- Frontend: ChatGPT tasks panel at the top of every step (copy prompt, open ChatGPT, answer box with fix prompt, image cards with drop/paste/click upload, references download, copy-all, bulk upload, skip), "Waiting for you" status, consistency pass/fail buttons, combined sheet, setup card, Settings toggle, en/ar strings.
- Tests: `tests/test_manual.py` (full manual book end to end through export, no duplicate tasks, validation errors + fix prompt, page count, bulk matching, skip rules, consistency verdicts + override, redo).

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
- Manual mode task keys include the job id (so "regenerate" asks again), except page images (`stable`: prompt + seed with the attempt), so a cancelled and restarted generation reuses uploaded pages.
- Manual-mode text tasks are created in a separate DB session; handlers must not hold uncommitted writes when they ask (all requests come before side effects).
- With no API key and `IMAGE_PROVIDER=mock` the app now starts in manual mode (plan §1 "auto"); mock-only use needs `MANUAL_MODE=0`. `tests/conftest.py` sets `MANUAL_MODE=0`.
- Analysis in manual mode keeps the fetched/uploaded source pictures until the ChatGPT answer arrives (the user must attach them), then deletes them as before.

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
- Verified in CI only (the build container had no PyPI/npm access). The frontend (including the manual-mode panel) has not been clicked through in a real browser yet.
- Manual mode has not been tried against real ChatGPT output yet; ChatGPT images often go close to the edges, so expect some pages flagged by the edge check (approve them in Review if they look fine).
- WeasyPrint/Pango and pypdfium2 are not thread-safe: all native PDF calls go through `render.raster.PDF_LOCK`. Keep using it for any new PDF code.
- WeasyPrint misplaces column-flex items in RTL: use block layout for centered page content.
- Fonts are not committed (downloaded by `make fonts`); PDFs fall back to DejaVu Sans / system Noto.
- No end-to-end run against real image/LLM providers has been done yet (needs keys); run the comparison harness first.
- Vision QA and consistency checks depend on the chosen LLM; with mocks they always pass.
- Hosted mode (v2: auth, HTTPS, rate limits) is out of scope.
