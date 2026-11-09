# Manual mode (ChatGPT Pro) – implementation plan

Goal: produce a whole book **without any paid API**, using the user's ChatGPT Pro subscription by copy/paste. The web app does everything that is free (fetching, planning logic, code-drawn pages, cleanup, QA checks, PDFs, Drive); every step that needs an AI model becomes a **ChatGPT task** the user does in ChatGPT and hands back. The cycle must feel smooth: few round trips, copy buttons, paste/drag-drop, validation with ready-made fix messages, automatic resume.

`PLAN.md` stays the source of truth; this file extends it. API mode and mock mode must keep working unchanged (all existing tests stay green).

## 1. Mode switch
- New setting `manual_mode` (bool or null = auto). Env `MANUAL_MODE=1|0`; auto = manual when there is no `ANTHROPIC_API_KEY` and `IMAGE_PROVIDER` is `mock`/`manual`.
- `services/manual.is_manual()` reads the setting (DB) with the env fallback.
- `tests/conftest.py` sets `MANUAL_MODE=0` so existing tests keep using mocks.
- Settings page: toggle "Manual mode (ChatGPT)" with a short explanation.

## 2. Data model (Alembic migration `0002_manual_tasks`)
`ManualTask`: id, book_id, job_id, kind (`text|image`), task (e.g. `propose_themes`, `page`, `candidate`), key (deterministic hash, unique per book), group (batch label shown in UI), title, prompt, meta JSON (schema model name, expected_count, ref asset paths, size/aspect, page_id, label, vars for tests), status (`pending|done|skipped`), answer_text, answer_path, created_at, answered_at.
Job status gains **`waiting`** (waiting for the user).

## 3. Backend mechanics
- `class AwaitingManual(Exception)` carrying the created task ids.
- Runner: catching `AwaitingManual` sets job `waiting` (message "Waiting for ChatGPT: N task(s)"); `claim_next` ignores waiting jobs; `active_job` and `cancel` include waiting. A contextvar holds the current job id + book id (set in `run_job`).
- Handlers are re-run from the start when the job resumes; answers are found by **deterministic keys** (hash of kind + task + prompt + seed/attempt), so nothing is asked twice. All image requests of a step are collected **before** any side effects.
- `services/manual.py`:
  - `request_text(task, prompt, model_name, meta)` → returns the stored answer or creates the task and raises.
  - `image_batch(book_id, group, task, items: list[ImageReq])` → API mode: calls the image provider for each item; manual mode: returns stored images, creates **all** missing tasks at once and raises. Skipped items return `None`.
  - `submit_text(task_id, text)`: extract JSON (fences tolerated), validate with the Pydantic model named in meta (+ `expected_count` check), on error return readable errors **and a fix prompt** to paste back into ChatGPT; on success store and resume.
  - `submit_image(task_id, bytes)`: validate (type/size/decode), save under `data/books/<id>/manual/`, mark done.
  - `bulk_images(book_id, files)`: match by number in the filename (`page_12.png` → task labelled 12), else in order to pending tasks.
  - `skip(task_id)`; `resume_if_ready(job_id)` re-queues the job when its pending tasks are all done/skipped.
- `providers/manual.py`: `ManualTextLLM` (TextLLM + VisionLLM) backed by `request_text`; registry returns it in manual mode (test overrides still win). `llm.structured()` passes the model name + extra meta and does no repair round trip in manual mode (validation happens at submit time). The prompt shown to the user ends with "Reply with ONE JSON object only…" + schema.

## 4. Per-step behaviour in manual mode (minimise round trips)
| Step | Manual behaviour | Round trips |
|---|---|---|
| Source analysis | App still fetches the store page for free; one text task. Prompt tells the user to attach any page screenshots in ChatGPT. | 1 text |
| Themes, formats, hybrid | One text task each. | 1 text each |
| Character briefs | One text task. | 1 text |
| Candidates | One batch of up to 4 image tasks (user may skip some; min 1). | 1 batch |
| Lock and edit | **No LLM**: prompt built by template ("same character as attached image, change only: …"); 1 image task with the selected image as reference. | 1 image |
| Character sheet | **One combined image** (front, side, 3/4 + happy, sleepy, surprised on one sheet) instead of 6. Stored as kind `sheet`, meta view `combined`; `sheet_images` accepts it. | 1 image |
| Consistency test | 3 test-scene image tasks (skippable); **user marks pass/fail per scene** in the UI (no vision call). Approval needs all marked pass, or override. | 1 batch |
| Sample page | 1 image task, prompt by template. | 1 image |
| Page plan | One text task; `plan_pages.md` also asks for a full image `prompt` per image page (`PlannedPage.prompt`), `expected_count` enforced at submit. | 1 text |
| Generation | Code pages rendered first (no tasks). Image pages registered **one batch at a time** (batch size 5/10 setting); each upload → programmatic QA → cleanup. No vision QA, no automatic redo; failing pages are marked failed with issues and shown first in Review. | N/batch |
| Review redo | Creates new image tasks (key includes attempt) with the user note + QA issues appended. | per redo |
| Content QA (`qa_content`) | Skipped. | 0 |
| Cover art | 1 image task (optional; a page can be used instead). | 0–1 |

Manual page prompt template (code, no LLM): one image per message, portrait aspect (choose ChatGPT's tall size), scene, characters "exactly like the attached reference images", style anchor rules, then fixed rules: pure white background, clean closed bold black outlines, no grey/shading/filled black areas, white margin around the drawing, **no text/letters/numbers**; plus user note / QA issues.

## 5. ChatGPT Project setup (quality)
Endpoint + card "Set up ChatGPT for this book": copyable **project instructions** (Book Brief text: style formula, theme, characters, line-art rules, originality + no-text rules, output conventions) and the list of **reference images to upload to the project** (style anchor + each character's sheet) with download buttons. All text tasks then work in one ChatGPT Project per book so context and characters stay consistent.

## 6. API
- `GET /api/books/{id}/manual` – pending + recent tasks grouped by job/group, refs as URLs.
- `POST /api/manual/{task_id}/text` `{text}` → 200 or 422 `{errors, fix_prompt}`.
- `POST /api/manual/{task_id}/image` (multipart) · `POST /api/books/{id}/manual/images` (bulk) · `POST /api/manual/{task_id}/skip`.
- `POST /api/books/{id}/characters/{cid}/consistency/verdict` `{asset_id, pass, issues?}`.
- `GET /api/books/{id}/chatgpt-setup`.
- Settings: `manual_mode`.

## 7. Frontend
- **ChatGPT tasks panel** shown at the top of every wizard step whenever the book has pending tasks:
  - Text task: prompt with Copy, "Open ChatGPT" link, answer textarea, Submit; on 422 show errors + a Copy button for the fix prompt.
  - Image batch: "Copy all prompts" (one message) + per-image cards (label, prompt Copy, reference thumbnails with download, drop zone that also accepts **Ctrl+V paste** of a copied image, preview, Skip); bulk upload input.
- Job status `waiting` shown as "Waiting for you in ChatGPT"; polling continues; the step continues by itself after the last answer.
- Characters step in manual mode: pass/fail buttons per test scene; combined sheet view.
- Settings toggle; ChatGPT setup card (Characters step and panel).
- All strings in `en.json` + `ar.json` (same keys; the i18n test enforces it). Logical CSS properties for RTL.

## 8. Tests (pytest, offline)
- Full book end to end in manual mode with a helper that answers every pending task (text: `providers.mock._canned(task, vars)`; images: `MockImageProvider`), through to export.
- Job goes `waiting` → answers → resumes → done; **no duplicate tasks** on re-run.
- Invalid JSON → 422 with readable errors + fix prompt; wrong page count rejected.
- Bulk upload filename matching; skip handling (skipped candidate not created; skipped page → failed).
- Consistency verdicts gate approval; override works.
- Existing API/mock tests unchanged and green.

## 9. Docs
README "Manual mode with ChatGPT" section (step-by-step cycle), STATE.md updated (decisions, dependencies unchanged).

## Work order (small commits)
1. Model + migration + `waiting` status in runner. 2. `services/manual.py` + manual provider + registry + `structured()` changes. 3. Characters/sample/cover/generation/planning manual paths. 4. API routes. 5. Frontend panel, consistency verdicts, setup card, settings toggle, i18n. 6. Tests. 7. README/STATE. Run `ruff` + `pytest` + frontend `npm test && npm run build` before pushing.
