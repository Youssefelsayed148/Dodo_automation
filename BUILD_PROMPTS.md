# Dodo Book Studio — Build Prompts for Claude Code

How to use: open a **fresh Claude Code session per prompt**, start in **plan mode**, paste one prompt, approve the plan, let it build, **commit at the end**. Do not skip steps or merge two prompts. After each step, paste Claude Code's report back to Claude (chat) for review before starting the next.

`PLAN.md` is the source of truth. If a prompt and the plan disagree, stop and ask.

---

## Prompt 0 — Repo, agent rules, state file

```
Read PLAN.md fully. Goal of this step: set up the repo skeleton only. No features.

Do:
1. Create the layout from PLAN.md section 5 (empty packages with __init__.py / placeholder files where needed).
2. Create AGENTS.md with these working rules: read PLAN.md and STATE.md at session start; work on exactly one step; plan first; small commits with clear messages; never add a dependency without listing it in STATE.md; never commit secrets; update STATE.md at the end; stop and ask when the plan is ambiguous.
3. Create STATE.md with: current step, done list, decisions made, open questions, how to run, known issues.
4. Create .gitignore (data/, .env, node_modules, __pycache__, .venv), .env.example (ANTHROPIC_API_KEY, IMAGE_PROVIDER=mock, DATABASE_URL=sqlite:///data/app.db, GOOGLE_CLIENT_ID/SECRET placeholders), and a short README.md.
5. Backend: pyproject.toml (FastAPI, uvicorn, SQLAlchemy, alembic, pydantic-settings, httpx, pillow, numpy, weasyprint, pytest). Frontend: Vite React TS app.
6. A single command to run both (Makefile or scripts) and a /health endpoint.

Acceptance: backend starts, GET /health returns ok; frontend dev server starts; pytest runs (one trivial test); git repo initialized with a first commit.
Do not build anything else.
```

## Prompt 1 — Database, settings, job runner, provider interfaces + mocks

```
Read AGENTS.md, STATE.md, PLAN.md sections 6, 9, 10, 18.

Build:
1. SQLAlchemy models for every table in section 6 + Alembic initial migration. SQLite in data/app.db.
2. Settings service (key/value) with defaults: batch_size=10, default trim size 8.5x11 in, default language en.
3. Persistent job runner (jobs/runner.py): async worker loop that picks queued Job rows, runs registered handlers, updates progress/status/error, retries failed jobs on request, resumes queued jobs after restart. Handlers registry in jobs/handlers.py.
4. Provider interfaces from section 9 (providers/base.py) plus MockImageProvider (draws simple black-outline placeholder art with Pillow), MockVisionLLM and MockTextLLM returning schema-valid canned JSON.
5. A real AnthropicLLM implementing TextLLM and VisionLLM (model name from env, not hard-coded), with retries/backoff and UsageLog writes.
6. Prompt loader that reads backend/prompts/*.md and fills {placeholders}; JSON-schema validated outputs with one repair retry.
7. REST: GET/PUT /api/settings, GET /api/jobs, GET /api/jobs/{id}, POST /api/jobs/{id}/retry.

Tests: job runner (success, failure, retry, resume), prompt loader, mock providers.
Acceptance: a test job runs to done with progress updates; restart resumes a queued job; all tests pass.
```

## Prompt 2 — Frontend shell, EN/AR with RTL, wizard

```
Read AGENTS.md, STATE.md, PLAN.md sections 7 and 16. Look at the approved prototype look: warm cream background, orange brand, Fredoka for headings and Nunito for body, rounded cards, sticky step bar on top and Back/Next bar at the bottom, light and dark themes.

Build the frontend shell only (no real backend calls yet beyond health/settings):
1. App layout, router, TanStack Query setup, API client with base URL from env.
2. react-i18next with en.json and ar.json; a header toggle that switches language, persists it (localStorage + settings API), sets <html lang dir>. Use CSS logical properties everywhere so RTL works. Arabic UI font: Cairo (or Noto Sans Arabic).
3. A "My books" list page (empty state) and a "New book" wizard with the 9 steps from section 7: step bar, Back/Next, per-step placeholder screens with real translated labels.
4. Theme tokens as CSS variables with light/dark (prefers-color-scheme) support.
5. No hard-coded user-facing strings in components.

Acceptance: switching to Arabic flips the whole layout to RTL with correct alignment and fonts; step navigation works on a 400px phone width and on desktop; build passes type checks.
```

## Prompt 3 — Source and analysis

```
Read AGENTS.md, STATE.md, PLAN.md sections 2, 7 (steps 1-2), 10, 17.

Backend:
1. POST /api/books (create) and source endpoints: submit URL, optional pasted description text, optional uploaded images/PDF (validate type/size; PDF -> up to 15 page images).
2. URL fetcher (httpx): http/https only, SSRF guard (block private/loopback/link-local after DNS resolution), timeouts, size cap. Extract title, description, og tags, JSON-LD product data, and up to 5 preview images. If fetching fails or content is thin, return a clear status asking the user to paste the description or upload images.
3. analysis service + prompt analyze_source.md: sends text + images to VisionLLM; returns a Recipe (mood, age_group, line_weight, detail_level, page_mix, confidence, notes). Confidence is "medium" for URL-only, "high" with uploaded pages, "low" if almost nothing was readable. The prompt must obey the originality rule: no character names, titles or brand terms from the source in the output.
4. Delete downloaded/uploaded source images after analysis completes. Run analysis as a job.
5. GET/PUT /api/books/{id}/recipe so every field is editable.

Frontend: steps 1 and 2 of the wizard wired to these endpoints, with a progress state for the analysis job and the editable recipe card with the confidence tag.

Tests: SSRF guard, fetcher parsing on saved HTML fixtures, analysis with the mock LLM, image cleanup after analysis.
Acceptance: pasting a link (or text) produces an editable recipe; thin pages show the "paste description" fallback.
```

## Prompt 4 — Themes, formats, page plan

```
Read AGENTS.md, STATE.md, PLAN.md sections 7 (steps 3-4), 8, 10.

Backend:
1. propose_themes.md: 3 original themes (title + description) from the Recipe. Regenerate endpoint.
2. propose_formats.md: 3-4 formats made of page-type blocks (types from section 8) with shares that sum to 100, based on the Recipe and the chosen theme. Support "ask for a new hybrid" with a free-text instruction.
3. plan_pages: given the chosen theme, format, page count and book language, create the Page rows: type, order, a one-line scene description for image pages, and text_content for code-drawn pages (story text, Q&A questions and answers, word lists). Every page description must be distinct from the others.
4. Endpoints: choose theme, rename title, choose/edit format blocks, plan pages, list/edit pages.

Frontend: steps 3 and 4: theme cards, editable title, format cards with an editable mix (sliders or number inputs that stay at 100%), and a read-only page list preview.

Tests: shares sum to 100, no duplicate scene descriptions, schema validation with the mock LLM.
Acceptance: from a recipe, the user gets themes, then formats, then a planned list of N pages.
```

## Prompt 5 — Characters (the quality-critical step)

```
Read AGENTS.md, STATE.md, PLAN.md section 11 and 12 (style anchor).

Build the full character workflow:
1. character_brief.md: per character, name, species, personality, proportions, one signature feature, outfit, derived from the theme.
2. Candidates: generate 4 candidates per character with the ImageProvider; store as CharacterAsset(kind=candidate); user selects one.
3. Lock-and-edit: free-text instruction -> character_edit.md produces a revised prompt; regenerate using the selected image as reference; keep history of versions.
4. Sheet: front, side, three-quarter views and 3 expressions (happy, sleepy, surprised) generated with the selected image as reference.
5. Style anchor: store the chosen line-style rules + reference image on the Book; helper that returns them for later generations.
6. Consistency test: draw each character in 3 test scenes; qa_vision_check compares to the sheet (face shape, signature feature present, line weight); show pass/fail with reasons. Approval needs a pass or an explicit user override.
7. Sample page: generate one full-style page using characters + style anchor; user approves or tries another.
8. Library: save approved characters; reuse them in a new book.

Frontend: step 5 with candidate grid, pick, edit box, sheet view, consistency result, sample page approval. All jobs show progress.

Tests: state transitions, history, library reuse, consistency verdict handling with the mock providers.
Acceptance: with the mock provider the full flow works end to end; approval gates block progress until satisfied.
```

## Prompt 6 — Real image providers and comparison harness

```
Read AGENTS.md, STATE.md, PLAN.md sections 9 and 20.

1. Implement ImageProvider for 2-3 real providers behind config (IMAGE_PROVIDER, model name, API key from env). Include reference-image support where the provider allows it. Keep provider/model names out of code logic.
2. Comparison harness: CLI + a Settings sub-page. Input: one theme, one approved character sheet, 10 page prompts. Run the same inputs through each configured provider and save outputs side by side in data/compare/<run>/.
3. For each output record: time, estimated cost (UsageLog), programmatic QA metrics, and a manual 1-5 score box for "clean closed outlines" and "matches character sheet". Show a table and a side-by-side image grid.
4. A setting to choose the winning provider/model per book or globally.

Do not pick a winner yourself. Print a summary table at the end.
Tests: provider adapters with recorded/mock HTTP responses, harness output structure.
Acceptance: harness runs on the mock provider with no keys, and on real providers when keys are present.
```

## Prompt 7 — Page generation, QA and cleanup

```
Read AGENTS.md, STATE.md, PLAN.md sections 8 and 12.

1. page_image_prompt.md builds each image prompt from: style anchor, character brief(s) present on the page, scene description, and "no text inside the image".
2. Generation job: batches of `batch_size` pages, configurable concurrency, per-page status updates, resumable after restart, cost logged.
3. QA service: programmatic checks (grey ratio after threshold, ink coverage range, subject touching edge) then VisionLLM check (qa_vision_check.md). Failed pages auto-redo up to 2 times with issues appended to the prompt, then become `failed`.
4. Cleanup (services/cleanup.py): grayscale, upscale to target pixels at 300 DPI (include bleed if enabled), threshold, despeckle, fit on canvas with 0.5in safe margin, save PNG with DPI metadata.
5. Endpoints: start generation, pause/cancel, status, per-page regenerate.

Frontend: step 6 (specs with live pixel size) and step 7 (progress bar, redo counter, current batch).

Tests: cleanup output size/DPI/pure black-and-white, QA decisions on fixture images, batch resume, retry limits.
Acceptance: with the mock provider a 40-page book generates, passes through QA, and resumes correctly after a forced restart.
```

## Prompt 8 — Code-drawn pages

```
Read AGENTS.md, STATE.md, PLAN.md section 8.

Implement in backend/app/render/ pure-code renderers that output print-size PNG or SVG-to-PNG pages with correct fonts, no image model:
- maze (solvable, difficulty by age), dot_to_dot (numbered points forming a given simple outline), word_search (words from the theme, answer key), trace_write (dotted letters/words), qa_page (question + answer lines or multiple choice), story_text (text block in a clean layout), title_page, belongs_to_page, end_page.
- All text must support English and Arabic (shaping + RTL) via WeasyPrint/HTML templates.
- Each renderer takes (page.text_content, book specs) and returns a file path; integrate with the generation job so these pages are created without calling the image provider.

Tests: maze solvability, word search contains all words, Arabic text renders (non-empty, correct direction check via template output), sizes match specs.
Acceptance: a book mixing image pages and code pages generates fully and in order.
```

## Prompt 9 — Review grid and redo

```
Read AGENTS.md, STATE.md, PLAN.md section 7 (step 8).

1. Review screen: grid of all pages (thumbnails), tap to mark rejected, page detail viewer with prompt, QA verdict, attempts.
2. "Redo N pages" regenerates only rejected pages (optionally with a short user note appended to the prompt), then returns to the grid.
3. Show failed pages first with a banner. Allow approving all at once.
4. Thumbnail generation and caching so a 100-page grid stays fast.

Tests: reject/redo state machine, only rejected pages are regenerated, notes appended to prompts.
Acceptance: reviewing 40 pages and redoing 3 takes one pass and leaves all other pages untouched.
```

## Prompt 10 — PDF assembly and cover

```
Read AGENTS.md, STATE.md, PLAN.md section 13.

1. interior.py: WeasyPrint-based assembly at exact trim+bleed page size: title page, optional "belongs to", pages in order, code-rendered page numbers, end page.
2. cover.py: front cover template with the title as live text (English or Arabic) over a chosen page image or a generated cover image; simple template choices.
3. Bundle fonts (Latin display + Noto Naskh Arabic or Cairo). Verify Arabic shaping and RTL.
4. Output to data/books/<id>/export/interior.pdf and cover.pdf. Add a PDF preview in the frontend.

Tests: page count, page size in points matches spec (with and without bleed), fonts embedded, Arabic title rendering.
Acceptance: a 40-page book produces a correct interior.pdf and cover.pdf for 8.5x11 in with 0.125in bleed.
```

## Prompt 11 — Google Drive export

```
Read AGENTS.md, STATE.md, PLAN.md section 14.

1. OAuth installed-app flow (localhost redirect), scope drive.file only. Store tokens in data/ with restrictive permissions; add a "Connect Google" and "Disconnect" control in Settings with connection status.
2. Export action: create a folder named after the book title (sanitize; if it exists use "Title (2)"), upload interior.pdf, cover.pdf, the pages/ images and book-settings.json. Return the folder link.
3. Make Drive optional per export; local export to data/books/<id>/export/ always happens.
4. Handle expired tokens, quota errors, partial upload (resume/skip existing).

Frontend: step 9: Drive toggle, folder name preview (editable), file list, progress, success with link.

Tests: folder naming/sanitizing, upload planning with a mocked Drive client.
Acceptance: with real credentials a book exports into a Drive folder named after its title; without credentials the toggle explains how to connect.
```

## Prompt 12 — Manual prompt export and import

```
Read AGENTS.md, STATE.md, PLAN.md section 15 and the Book Brief idea in section 2.

1. Brief builder: one function that serializes the Book Brief (recipe as text, source description text, theme, format mix, characters, line-art rules, specs, originality rule) used by both the app and the exports.
2. Planning prompt export: self-contained text asking a chat assistant to return the numbered page list with an image prompt per page as JSON matching the Page schema. Copy button + .md download.
3. Page prompt pack: batches of 5 or 10 (setting). Each batch = short shared header + numbered page prompts; code-drawn pages excluded. Copy button and a done checkbox per batch.
4. Import: paste JSON or a numbered list; validate against the schema; show a diff and create/replace Page rows.
5. Frontend: an "Export prompts" panel available from step 4 onward.

Tests: round trip (export -> import -> same pages), schema validation errors are readable, batch splitting at 5 and 10.
Acceptance: copying the planning prompt into a chat and pasting back the JSON recreates the page plan and the app continues.
```

## Prompt 13 — Hardening, cost view, docs

```
Read AGENTS.md, STATE.md, PLAN.md sections 17, 18, 21.

1. Cost view: per book and per page (generated + redone) from UsageLog; per-book cost ceiling setting that pauses generation when reached.
2. Error states and empty states in every wizard step; clear messages in both languages.
3. Full Arabic pass: every string translated, RTL checked on every screen, Arabic PDF verified.
4. Security pass: .env handling, SSRF tests, upload validation, localhost binding, token file permissions.
5. Backup/export of a whole book folder (zip) and re-import.
6. README: setup, env vars, running with the mock provider, running the comparison harness, connecting Drive, troubleshooting.
7. Run the full test suite and a complete end-to-end run on the mock provider; list remaining known issues in STATE.md.

Acceptance: every item in PLAN.md section 21 passes; STATE.md is current.
```

---

## After v1 (separate plan, do not start yet)

Hosting on a small server with a login gate, sticker-sheet layout, full cover wrap with spine, character library browser, Instagram teaser posts from finished pages.
