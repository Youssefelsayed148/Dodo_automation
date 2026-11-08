# Dodo Book Studio — Product & Technical Plan

Working name: **Dodo Book Studio**. A personal tool for Dodo Books (coloring books, stickers, activity books). One user, no accounts. English/Arabic UI toggle.

## 1. Purpose

Turn "a book I like" (store link, optional pages) into a finished, print-ready, **original** book with minimal manual work:

1. Read the liked book's store page (and optional uploaded pages) and extract its *formula* (mood, page mix, detail level, age group).
2. Propose original themes and book formats built from that formula.
3. Create and approve characters once.
4. Generate all pages at print size with automatic quality checks.
5. Review all pages in one grid, redo only the bad ones.
6. Build the interior PDF + cover, optionally upload to a Google Drive folder named after the book.
7. Also export the same plan as **prompts** the user can paste manually into Claude or ChatGPT.

The user's time goes into: choosing a link, picking a theme, approving characters, reviewing the grid. Everything else is automated.

## 2. Rules that apply everywhere

- **Originality.** Only the abstract formula of the reference book is reused (mood, structure, page mix, detail level). Never reuse its characters, names, titles, scenes, text or brand. Analysis output must not contain the source's character names or trademarks. Source images are used for analysis only and are not stored after analysis.
- **No text inside generated images.** The image model never draws letters. All text (titles, story, questions, page numbers) is rendered by code. This keeps spelling correct, especially Arabic.
- **One source of truth: the Book Brief.** The app and the manual prompt export are both generated from the same structured brief (section 15).
- **Human approval gates:** characters, sample page, final review grid. Everything between gates runs without supervision.
- **Provider-agnostic.** Image/vision/text models sit behind interfaces; the model is chosen by config, after a comparison test (section 9).
- **Everything resumable.** Closing the browser never loses work; long jobs run in the backend.

## 3. Platform

- Web app, **local-first (v1)**: backend on `127.0.0.1`, frontend opened in the browser. Single user, no login.
- Hosting on a small server is a later phase (v2): same code, adds a login gate. Nothing in v1 may make that impossible (no hard-coded localhost paths in the frontend, config via env).

## 4. Tech stack

- Backend: **Python 3.12, FastAPI**, SQLAlchemy 2.x, Alembic, Pydantic v2, httpx.
- DB: **SQLite** in v1 (single file in `data/`), written with SQLAlchemy so PostgreSQL is a config change later.
- Jobs: in-process async worker with a **DB-persisted job table** (no Redis). Jobs survive restarts and can be retried.
- Frontend: **React + TypeScript + Vite**, React Router, TanStack Query, **react-i18next** (en/ar), plain CSS with variables (match the approved prototype look).
- Images: Pillow, NumPy (and OpenCV only if needed for QA).
- PDF: **WeasyPrint** (HTML/CSS pages, correct Arabic shaping, exact page size and bleed).
- LLM/vision: Anthropic API (Claude) by default behind an interface.
- Google Drive: `google-api-python-client`, OAuth installed-app flow, scope `drive.file`.
- Tests: pytest (backend), Vitest (frontend core logic).

## 5. Repo layout

```
dodo-studio/
  AGENTS.md  STATE.md  PLAN.md  BUILD_PROMPTS.md  README.md
  .env.example
  backend/
    app/
      main.py  config.py  db.py  models.py  schemas.py
      api/            # routers: books, sources, themes, characters, pages, jobs, export, settings
      services/       # analysis, planning, characters, generation, qa, cleanup, export_prompts
      providers/      # base.py, mock.py, anthropic_llm.py, image_*.py
      jobs/           # runner.py, handlers.py
      render/         # code-drawn pages: maze, word_search, dot_to_dot, qa_page, story_page
      pdf/            # interior.py, cover.py, templates/, fonts/
      prompts/        # versioned LLM prompt files (*.md) with {placeholders}
    tests/
  frontend/
    src/ pages/ components/ api/ i18n/{en.json,ar.json} styles/
  data/               # gitignored: db, books/<id>/..., tokens
```

## 6. Data model (SQLAlchemy; JSON columns for flexible parts)

- **Book**: id, title, status (`draft|analyzed|themed|characters|specced|generating|review|exported`), source_type (`url|url_pages|text|none`), source_url, source_text, book_language (`en|ar`), trim_size, bleed (bool), page_count, theme_id, format_id, created_at.
- **Recipe** (1:1 Book): mood, age_group, line_weight, detail_level, page_mix (JSON), confidence (`high|medium|low`), notes.
- **ThemeOption**: book_id, title, description, chosen (bool).
- **FormatOption**: book_id, name, blocks (JSON: `[{type, share}]`), description, chosen (bool).
- **Character**: id, book_id (nullable for library), name, species, personality, signature_feature, proportions, brief (JSON), status (`draft|approved`), in_library (bool).
- **CharacterAsset**: character_id, kind (`candidate|sheet|expression|test_scene`), path, selected (bool), meta (JSON).
- **Page**: book_id, index, type, prompt, text_content (JSON), status (`planned|queued|generated|failed|approved|rejected`), image_path, qa (JSON), attempts, batch_no.
- **Job**: id, book_id, type, payload (JSON), status (`queued|running|done|failed|cancelled`), progress (0–1), error, created/updated.
- **UsageLog**: provider, model, kind, units, est_cost_usd, book_id, at.
- **Setting**: key/value (provider choices, batch size 5|10, default trim size, default language).

## 7. User flow (maps to the approved prototype)

1. **Source**: store link (default), link + optional uploaded pages/PDF, or typed theme only. Optionally paste the store description text (used when the page cannot be fetched).
2. **Style**: detected recipe shown with a confidence tag; every field editable.
3. **Theme**: 3 original proposals; pick one; rename the title.
4. **Format**: 3–4 *proposed formats* built from page-type blocks, based on the analyzed book and the chosen theme (not a fixed list). Editable block mix. User can ask for a new hybrid.
5. **Characters**: brief → 4 candidates per character → pick → lock-and-edit → expression sheet → consistency test → approve → sample page → approve.
6. **Specs**: page count, trim size, bleed, book language, shows pixel size per page at 300 DPI.
7. **Generate**: batches with progress, automatic QA, automatic redo.
8. **Review**: grid of all pages, tap to reject, redo only those.
9. **Export**: interior PDF, cover PDF, approved page images, `book-settings.json`; optional Drive upload into a folder named after the title. Also "Export prompts" (section 15).

## 8. Page types and who draws them

Image-model pages: `single_character`, `scene`, `pattern_mandala`, `hidden_objects_scene`.
Code-drawn pages (cheap, always correct): `maze`, `dot_to_dot`, `word_search`, `trace_write`, `qa_page`, `story_text`, `title_page`, `belongs_to_page`, `end_page`.

A **format** = a named mix of these types with shares and a layout order. Example: "Color and bake" = 60% scene, 20% single_character, 10% qa_page, 10% maze. The LLM proposes formats from the recipe and theme; the user edits shares.

## 9. Provider layer

```
ImageProvider.generate(prompt, size_hint, reference_images=[], seed=None) -> bytes
VisionLLM.analyze(images, prompt, schema) -> dict
TextLLM.complete(prompt, schema=None) -> str | dict
```

- Implementations are chosen by `Setting`/env. Always ship a **MockImageProvider** (draws placeholder line art) so the whole pipeline can be built and tested at zero cost.
- **Model comparison harness (required before choosing an image model):** same 10 page prompts and the same character sheet through 2–3 candidate providers; save outputs side by side; record cost, time, redo rate, and a manual 1–5 score for outline cleanliness and character consistency. Provider and model names are configuration, not code.
- Retries with backoff, timeouts, rate-limit handling, and cost logging in one place.

## 10. LLM prompt system

All LLM prompts live in `backend/prompts/*.md`, versioned, with `{placeholders}`. Structured outputs use JSON schemas validated by Pydantic; on invalid JSON, one automatic repair retry.

Required prompts: `analyze_source`, `propose_themes`, `propose_formats`, `plan_pages`, `character_brief`, `character_edit`, `page_image_prompt`, `story_text`, `qa_content`, `qa_vision_check`, `planning_prompt_export`.

Every prompt that touches the reference book includes the originality rule from section 2.

## 11. Character system

1. **Brief**: per character: name, species, personality, proportions (e.g. big head, small body), one **signature feature** (patched ear, scarf), outfit.
2. **Candidates**: 4 options per character; the user picks one.
3. **Lock and edit**: the user types an instruction ("shorter ears", "rounder face"); only that changes, everything else is held via the selected image as reference.
4. **Sheet**: front, side, three-quarter views + 3 expressions (happy, sleepy, surprised).
5. **Style anchor**: the line style chosen at this stage is attached (as reference + text rules) to every later generation.
6. **Consistency test**: each character drawn in 3 test scenes; vision check compares to the sheet (face shape, signature feature present, line weight). Approval is allowed only when it passes or the user overrides.
7. **Sample page**: one full-style page; user approves before the batch run.
8. **Library**: approved characters can be saved and reused in other books.

Known limit: no model keeps characters identical on every page. The design reduces drift (references, simple scenes, QA, redo); it does not promise zero drift.

## 12. Generation, QA and cleanup

- Generation runs as jobs in **batches** (batch size setting: 5 or 10), up to N concurrent calls (configurable), each page with: style rules, character sheet reference, page prompt.
- **Programmatic QA first (cheap):** grey-pixel ratio after thresholding, ink coverage within a sane range, subject not touching page edge, big open outline check (approximate).
- **Vision QA second:** JSON verdict `{pass, issues[]}` for shading/fills, text or letters present, cropped subject, missing signature feature, malformed anatomy.
- Failed pages auto-redo up to 2 times with the issues appended to the prompt; after that they are marked `failed` and shown in review.
- **Cleanup:** grayscale → upscale to target → threshold to pure black/white → despeckle → fit on the page canvas with safe margin (0.5 in) → save PNG with 300 DPI metadata.
- Defaults: 300 DPI; bleed 0.125 in when enabled; sizes: A4, A5, 8.5x11 in, 8x10 in, 6x9 in, custom.

## 13. PDF assembly

- WeasyPrint with an HTML/CSS template per page type; exact `@page` size (trim + bleed); fonts bundled: Latin display + **Noto Naskh Arabic** (or Cairo) for Arabic text.
- Interior: title page, optional "this book belongs to", pages in order, page numbers (code-rendered), end page.
- Cover: template with the title as live text over generated or chosen art, front only in v1 (full wrap with spine is later).
- Output: `interior.pdf`, `cover.pdf`.

## 14. Google Drive export

- OAuth installed-app flow on localhost, scope `drive.file` (only files the app creates). Token stored in `data/` with restrictive permissions, gitignored.
- On export: create a folder named after the book title (sanitized; if it exists, use `Title (2)`), upload `interior.pdf`, `cover.pdf`, `pages/` and `book-settings.json`. Show the folder link.
- Drive is optional per export; local files are always written to `data/books/<id>/export/`.

## 15. Manual prompt export and import

From a finished brief the app produces, as copyable text and as a `.md` download:
- **Planning prompt**: self-contained (recipe written out, store description pasted as text, theme, format mix, character briefs, line-art rules, specs, originality rule, required output format). Asks the chat to return a numbered page list with an image prompt per page as JSON.
- **Page prompt pack**: per-batch messages (batch size 5 or 10). Each batch repeats a short shared header (style rules, character brief, "use the attached character sheet", "no text in the image"), then numbered page prompts. Code-drawn pages are excluded. Each batch has a copy button and a done checkbox.
- **Import back**: paste the chat's JSON/numbered list; validate against the page schema; create or replace `Page` rows; the app continues (generation, QA, PDF).

## 16. Language: English / Arabic

- UI language toggle in the header; persisted; sets `<html lang dir>`; full RTL layout using CSS logical properties (`margin-inline-start`, etc.); Arabic UI font (Cairo or Noto Sans Arabic).
- **All UI strings** live in `en.json` / `ar.json`; no hard-coded text in components.
- **Book language is separate** from UI language (a user can run the UI in English and build an Arabic book). It drives story/Q&A text generation and PDF fonts and direction.
- Arabic correctness in PDFs is a release criterion (shaping, direction, numerals).

## 17. Security and privacy

- Secrets only in `.env` (git-ignored). `.env.example` committed. Backend bound to `127.0.0.1`.
- URL fetching: only `http/https`, resolve and block private/loopback/link-local IPs (SSRF guard), size and time limits, no cookies.
- Upload validation: type, size, image decode check.
- Source images deleted after analysis. No third-party analytics.
- When hosted later (v2): auth gate, HTTPS, rotate keys, per-request rate limits.

## 18. Cost tracking

Every provider call writes a `UsageLog` row. The UI shows estimated cost per book and per page (generated + redone) so the real cost per book is known.

## 19. Out of scope for v1

Accounts and multi-user, payments, mobile app, full cover wrap with spine, publishing to marketplaces, hosted deployment, automatic Instagram posting, sticker-sheet layout (planned next).

## 20. Open decisions (resolved by the comparison harness, not guessed)

- Which image provider/model for line art and for reference-based consistency.
- Whether batch size 10 works with the chosen image tool for manual use, else 5.
- Default concurrency and per-book cost ceiling.

## 21. Definition of done (v1)

- A book can go from a store link to `interior.pdf` + `cover.pdf` with only these manual actions: pick theme, approve characters and sample, review grid.
- Full UI works in English and Arabic with correct RTL.
- Whole pipeline runs with the Mock provider offline and in CI.
- Prompt export/import round-trips.
- Drive upload creates a folder named after the book title.
- Tests pass; README explains setup, `.env`, and the comparison harness.
