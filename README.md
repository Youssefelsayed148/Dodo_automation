# Dodo Book Studio

A personal, local-first tool that turns *a book you like* (store link, optional pages) into a finished, print-ready, **original** coloring / activity book: interior PDF + cover PDF, with an optional upload to a Google Drive folder named after the book. English/Arabic UI, English or Arabic books.

The plan lives in [`PLAN.md`](PLAN.md); progress and decisions in [`STATE.md`](STATE.md).

## What you do vs. what is automated

You: paste a link → pick a theme → approve characters and a sample page → review the page grid.
The app: reads the store page, extracts the style *formula*, proposes themes and formats, plans the pages, draws every page in batches with automatic quality checks and redo, renders puzzles and text by code, and builds the PDFs.

## Requirements

Docker (with Compose v2) and `make`. Nothing else: Python, Node and the WeasyPrint/Pango libraries all live inside the images.

## Run it (one command)

```bash
make up        # builds both images and starts the app: http://127.0.0.1:8080
```

Optional: copy `.env.example` to `.env` and fill in keys (see below); then `make up` again. Without a `.env` the app starts in manual mode with mock providers.

| Command | What it does |
|---|---|
| `make up` | build + start (UI on `WEB_PORT`, default 8080; health: `/health`) |
| `make down` | stop, keep data |
| `make logs` | follow logs |
| `make test` | lint + backend pytest + frontend tests/typecheck, in containers, offline |
| `make compare ARGS="--providers mock,openai"` | image model comparison harness |
| `make reset` | stop and **delete all data** |

Two containers: `backend` (FastAPI + job worker, SQLite and all books in the `dodo-data` volume, mounted at `/data`) and `web` (nginx serving the built UI and proxying `/api` to the backend). Fonts (Fredoka, Nunito, Noto Naskh Arabic, Cairo) are downloaded during the image build; offline builds fall back to system fonts. The database is migrated automatically on start.

## Environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude for analysis, planning, prompts and vision QA. Empty = offline mocks. |
| `ANTHROPIC_MODEL` | Claude model id (default `claude-opus-5-5`). |
| `TEXT_PROVIDER`, `VISION_PROVIDER` | `anthropic` or `mock` (default: `anthropic` when a key is set). |
| `IMAGE_PROVIDER` | `mock`, `openai` or `gemini` (can also be chosen in Settings, globally or per book). |
| `OPENAI_API_KEY`, `OPENAI_IMAGE_MODEL` | OpenAI image adapter (reference images via the edits endpoint). |
| `GEMINI_API_KEY`, `GEMINI_IMAGE_MODEL` | Gemini image adapter (inline reference images). |
| `COST_TABLE` | Optional cost overrides used for estimates (see `.env.example`). |
| `DATABASE_URL`, `DATA_DIR` | SQLite file and data folder (set by Docker: `/data` volume). |
| `WEB_PORT` | Host port of the UI (default 8080, bound to 127.0.0.1 only). |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google Drive export (optional). |
| `MANUAL_MODE` | `1` = manual mode with ChatGPT, `0` = API/mock providers, empty = auto (manual when there is no `ANTHROPIC_API_KEY` and `IMAGE_PROVIDER=mock`). Settings can override it. |

## Manual mode with ChatGPT (no paid API)

With a ChatGPT subscription and no API keys you can still make a whole book: the app does everything that is free (store page fetch, page planning logic, puzzles and text pages, cleanup, quality checks, PDFs, Drive), and every step that needs an AI model becomes a **ChatGPT task** that you run in ChatGPT and hand back.

Manual mode is on automatically when `ANTHROPIC_API_KEY` is empty and `IMAGE_PROVIDER=mock`; force it with `MANUAL_MODE=1|0` or in **Settings → Manual mode (ChatGPT)**.

**The cycle (for every step):**

1. Click the step's button as usual (e.g. *Propose themes*). The job pauses with the status **Waiting for you** and a **Your turn in ChatGPT** panel appears at the top of the step.
2. **Text task** (analysis, themes, formats, character briefs, page plan): click **Copy prompt**, paste it into ChatGPT, copy ChatGPT's whole reply and paste it into the answer box → **Submit answer**. The reply is validated; if something is wrong you see readable errors and a **Copy fix message** button – paste that into the same chat and submit the new reply.
3. **Image task** (character options, edits, sheet, test scenes, sample page, book pages, cover): **Copy prompt** (or **Copy all prompts** for a batch – ChatGPT makes one image per reply, write “next” after each), download the reference pictures shown on the card and attach them in ChatGPT, then drop the image on the card, paste it with **Ctrl+V**, or click to upload. For a batch, **Upload several images** matches files named `page_12.png` to page 12 and fills the rest in order. Optional images (a 4th character option, a test scene, a page, the cover) can be **skipped**.
4. After the last answer the job **continues by itself** and the step updates.

**Fewest round trips:** one text task per planning step; character options come as one batch of up to 4; lock-and-edit needs no text round trip (the prompt is a template); the character sheet is **one combined image** (3 views + 3 expressions); you judge the 3 consistency test scenes yourself with **Looks right / Not right**; the page plan already contains every page's image prompt; code-drawn pages (mazes, word search, dot-to-dot, story, Q&A, title, end) need no ChatGPT at all; image pages arrive one batch at a time (batch size 5 or 10 in Settings). There is no vision QA and no automatic redo in manual mode: the free programmatic checks still run, failing pages are shown first in Review, and **Redo** creates new tasks with your note and the problems appended.

**Set up ChatGPT once per book (recommended):** the **Set up ChatGPT** button (tasks panel and Characters step) gives you a project name, copyable **project instructions** (style formula, theme, characters, line-art, originality and no-text rules, answer conventions) and the **reference images** to upload (style reference and each character's sheet). Create one ChatGPT Project per book with these and run all tasks in chats inside it, so style and characters stay consistent. Update the instructions after you approve the characters.

## Running with the mock provider (no keys, no cost)

Leave all keys empty and set `MANUAL_MODE=0` in `.env` (otherwise the app starts in manual mode). The mock image provider draws placeholder line art and the mock LLMs return schema-valid canned JSON, so the whole wizard – including PDFs – works offline. This is also what the test suite and CI use.

## Choosing the image model: comparison harness

```bash
make compare ARGS="--providers mock,openai,gemini"
```

or **Settings → Compare image models** in the app. The same 10 page prompts (and character sheet) go through each configured provider. Outputs are saved side by side in `data/compare/<run>/`, with time, estimated cost and programmatic QA per image. Score each image 1–5 for “clean closed outlines” and “matches character sheet” in the app; the summary table updates. The harness never picks a winner – choose it in Settings (or per book in the Specs step).

## Google Drive

1. In Google Cloud console create an OAuth client of type **Desktop app** and enable the Drive API.
2. Put the client id/secret in `.env`, restart the backend.
3. **Settings → Google Drive → Connect Google**. The scope is `drive.file` (the app only sees files it created). The token is stored in `data/google_token.json` with `0600` permissions.
4. In the Export step tick “Also upload to Google Drive”. A folder named after the book title is created (`Title (2)` if it exists) with `interior.pdf`, `cover.pdf`, `pages/` and `book-settings.json`. Interrupted uploads resume and skip files already uploaded. Local files are always written to `data/books/<id>/export/`.

## Manual prompts (Claude / ChatGPT)

From step 4 on, **Export prompts** opens a panel with a self-contained planning prompt, per-batch page prompt packs (5 or 10 per batch, code-drawn pages excluded) with copy buttons and done checkboxes, a `.md` download, and an import box that accepts the chat’s JSON or a numbered list, shows a diff and replaces the page plan.

## Project layout

```
backend/app/
  api/        REST routers (books, themes, characters, pages, export, settings, jobs, compare, files)
  services/   analysis, planning, characters, generation, qa_checks, cleanup, export, export_prompts, drive, backup, compare
  providers/  base interfaces, mock, anthropic_llm, image_http (openai, gemini), registry
  jobs/       persistent DB-backed job runner + handlers
  render/     code-drawn pages (maze, word search, dot-to-dot, text pages)
  pdf/        interior + cover (WeasyPrint), fonts/
  prompts/    versioned LLM prompt files
frontend/src/ pages (wizard steps), components, api client, i18n (en/ar), styles
data/         git-ignored: database, books/<id>/…, compare runs, tokens
```

## Troubleshooting

- **The store page cannot be read** (robot check, blocked) – paste the description text and/or upload a few pages; analysis then runs on those.
- **“That link is not allowed”** – only public `http/https` addresses are fetched (private, loopback and link-local addresses are blocked).
- **Generation stopped with “cost ceiling reached”** – raise the ceiling in Settings and press Resume; finished pages are kept.
- **The backend was restarted mid-generation** – jobs resume automatically; only unfinished pages are processed.
- **Arabic looks wrong in PDFs** – the font download during the build probably failed; run `make up` again with network access (system Noto/DejaVu is the fallback).
- **Port in use** – set `WEB_PORT=8081` in `.env` and run `make up` again.
