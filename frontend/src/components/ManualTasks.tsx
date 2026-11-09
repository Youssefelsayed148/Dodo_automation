// Manual mode (ChatGPT): the tasks panel shown at the top of every wizard step,
// and the "Set up ChatGPT for this book" card.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError, url } from "../api/client";
import type { Book, ManualGroup, ManualTask } from "../api/types";
import { CopyButton, ErrorBox, Tag } from "./ui";

/** Whether manual (ChatGPT) mode is active, from the settings endpoint. */
export function useManualMode(): boolean {
  const s = useQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 30_000 });
  return !!s.data?.manual?.active;
}

const BOOK_QUERIES = ["book", "characters", "pages", "gen-status", "cost", "plan-preview", "chatgpt-setup"];

export default function ManualTasksPanel({ book }: { book: Book }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [setupOpen, setSetupOpen] = useState(false);
  const q = useQuery({ queryKey: ["manual", book.id], queryFn: () => api.manualTasks(book.id), refetchInterval: 2500 });
  const refreshTasks = () => qc.invalidateQueries({ queryKey: ["manual", book.id] });

  // When a job of this book changes state (e.g. it resumed and finished after
  // the last answer), refresh what the steps show.
  const activeKey = (q.data?.active_jobs ?? []).map((j) => `${j.id}:${j.status}`).join(",");
  const prev = useRef<string | null>(null);
  useEffect(() => {
    if (prev.current !== null && prev.current !== activeKey) {
      BOOK_QUERIES.forEach((k) => qc.invalidateQueries({ queryKey: [k, book.id] }));
      qc.invalidateQueries({ queryKey: ["job"] });
    }
    prev.current = activeKey;
  }, [activeKey, book.id, qc]);

  if (!q.data?.manual_mode) return null;
  const groups = q.data.groups;
  if (groups.length === 0) return null;
  const open = q.data.pending.length;

  return (
    <section className="card manual-panel stack" aria-live="polite" aria-label={t("manual.panel_title")}>
      <div className="row">
        <h3 style={{ margin: 0 }}>{t("manual.panel_title")}</h3>
        <Tag kind="warn">{t("manual.open_count", { count: open })}</Tag>
        <span className="spacer" />
        <button className="btn small" onClick={() => setSetupOpen(!setupOpen)}>
          {setupOpen ? t("common.hide") : t("manual.setup_open")}
        </button>
        <a className="btn small primary" href={q.data.chatgpt_url} target="_blank" rel="noopener noreferrer">
          {t("manual.open_chatgpt")}
        </a>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        {t("manual.panel_help")}
      </p>
      {setupOpen && <ChatGptSetupCard book={book} />}
      {groups.map((g) =>
        g.kind === "text" ? (
          g.tasks.map((task) => <TextTaskCard key={task.id} task={task} onDone={refreshTasks} />)
        ) : (
          <ImageGroupCard key={g.key} bookId={book.id} group={g} onDone={refreshTasks} />
        ),
      )}
    </section>
  );
}

const titleKey = (task: ManualTask | ManualGroup) => `manual.tasks.${task.task}`;
const titleOpts = (task: ManualTask | ManualGroup, name?: string | null) => ({ defaultValue: task.task.replace(/_/g, " "), name: name ?? "" });

function RefList({ refs }: { refs: ManualTask["refs"] }) {
  const { t } = useTranslation();
  if (refs.length === 0) return null;
  return (
    <div className="manual-refs">
      {refs.map((r) => (
        <a key={r.index} className="manual-ref" href={url(r.url)} download={r.name} target="_blank" rel="noopener noreferrer"
           title={t("manual.download")}>
          <img src={url(r.url)} alt={t("manual.reference", { n: r.index + 1 })} loading="lazy" />
          <span className="small">⬇ {t("manual.reference", { n: r.index + 1 })}</span>
        </a>
      ))}
    </div>
  );
}

interface FixInfo {
  errors: string[];
  fix_prompt: string;
}

function TextTaskCard({ task, onDone }: { task: ManualTask; onDone: () => void }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [fix, setFix] = useState<FixInfo | null>(null);
  const submit = useMutation({
    mutationFn: () => api.answerText(task.id, text),
    onSuccess: () => {
      setText("");
      setFix(null);
      onDone();
    },
    onError: (e) => {
      const d = e instanceof ApiError ? (e.details as FixInfo | undefined) : undefined;
      setFix(e instanceof ApiError && e.status === 422 && d && Array.isArray(d.errors) ? d : null);
    },
  });
  return (
    <div className="manual-task stack">
      <div className="row">
        <strong>{t(titleKey(task), titleOpts(task, task.character))}</strong>
        <span className="spacer" />
        <CopyButton text={task.prompt} label={t("manual.copy_prompt")} primary />
      </div>
      <div className="small muted">{t("manual.text_steps")}</div>
      {task.refs.length > 0 && (
        <div>
          <div className="small">{t("manual.attach_refs")}</div>
          <RefList refs={task.refs} />
        </div>
      )}
      <details>
        <summary className="small">{t("manual.show_prompt")}</summary>
        <pre>{task.prompt}</pre>
      </details>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t("manual.answer_placeholder")}
        aria-label={t("manual.answer_placeholder")}
        dir="auto"
      />
      <div className="row">
        <button className="btn primary" disabled={!text.trim() || submit.isPending} onClick={() => submit.mutate()}>
          {t("manual.submit")}
        </button>
      </div>
      {fix ? (
        <div className="alert error stack" role="alert">
          <strong>{t("manual.invalid")}</strong>
          <ul style={{ margin: 0 }}>
            {fix.errors.map((er) => (
              <li key={er}>{er}</li>
            ))}
          </ul>
          <div className="row">
            <CopyButton text={fix.fix_prompt} label={t("manual.copy_fix")} />
            <span className="small">{t("manual.fix_help")}</span>
          </div>
        </div>
      ) : (
        <ErrorBox error={submit.error} />
      )}
    </div>
  );
}

function ImageGroupCard({ bookId, group, onDone }: { bookId: number; group: ManualGroup; onDone: () => void }) {
  const { t } = useTranslation();
  const first = group.tasks[0];
  const bulkRef = useRef<HTMLInputElement>(null);
  const bulk = useMutation({ mutationFn: (files: File[]) => api.answerImagesBulk(bookId, files), onSuccess: onDone });
  const multi = group.tasks.length > 1;
  return (
    <div className="manual-task stack">
      <div className="row">
        <strong>{t(titleKey(group), titleOpts(group, first?.character))}</strong>
        <Tag>{t("manual.left", { count: group.tasks.length })}</Tag>
        <span className="spacer" />
        {group.all_prompts && <CopyButton text={group.all_prompts} label={t("manual.copy_all")} primary />}
        {multi && (
          <>
            <button className="btn small" onClick={() => bulkRef.current?.click()} disabled={bulk.isPending}>
              {t("manual.bulk_upload")}
            </button>
            <input
              ref={bulkRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              multiple
              hidden
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                e.target.value = "";
                if (files.length) bulk.mutate(files);
              }}
            />
          </>
        )}
      </div>
      <div className="small muted">
        {t("manual.image_steps")}
        {group.all_prompts && <> · {t("manual.copy_all_help")}</>}
        {multi && <> · {t("manual.bulk_help")}</>}
      </div>
      {bulk.data && (
        <div className="alert ok small">
          {t("manual.bulk_result", { matched: bulk.data.matched.length, unmatched: bulk.data.unmatched.length })}
          {bulk.data.errors.map((er) => (
            <div key={er}>{er}</div>
          ))}
        </div>
      )}
      <ErrorBox error={bulk.error} />
      <div className="manual-grid">
        {group.tasks.map((task) => (
          <ImageTaskCard key={task.id} task={task} onDone={onDone} />
        ))}
      </div>
    </div>
  );
}

function ImageTaskCard({ task, onDone }: { task: ManualTask; onDone: () => void }) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const up = useMutation({ mutationFn: (f: File) => api.answerImage(task.id, f, f.name || "image.png"), onSuccess: onDone });
  const skip = useMutation({ mutationFn: () => api.skipTask(task.id), onSuccess: onDone });
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const accept = (f: File | null | undefined) => {
    if (!f || !f.type.startsWith("image/")) return;
    setPreview(URL.createObjectURL(f));
    up.mutate(f);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    accept(e.dataTransfer.files?.[0]);
  };
  const onPaste = (e: ClipboardEvent) => {
    const item = Array.from(e.clipboardData.items).find((i) => i.type.startsWith("image/"));
    if (item) {
      e.preventDefault();
      accept(item.getAsFile());
    }
  };
  const label = task.page_index ? t("manual.page_n", { label: task.label }) : t("manual.image_n", { label: task.label });
  return (
    <div className="manual-image stack">
      <div className="row">
        <strong>{label}</strong>
        <span className="spacer" />
        <CopyButton text={task.prompt} label={t("manual.copy_prompt")} />
      </div>
      {task.scene && <div className="small muted">{task.scene}</div>}
      <details>
        <summary className="small">{t("manual.show_prompt")}</summary>
        <pre>{task.prompt}</pre>
      </details>
      {task.refs.length > 0 && (
        <div>
          <div className="small">{t("manual.attach_refs")}</div>
          <RefList refs={task.refs} />
        </div>
      )}
      <div
        className={`dropzone ${over ? "over" : ""}`}
        role="button"
        tabIndex={0}
        aria-label={t("manual.drop_here")}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        onPaste={onPaste}
      >
        {preview ? <img src={preview} alt={label} /> : <span className="small muted">{t("manual.drop_here")}</span>}
        {up.isPending && <span className="small">{t("manual.uploading")}</span>}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        hidden
        onChange={(e) => {
          accept(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      {task.skippable && (
        <div className="row">
          <button className="btn small ghost" onClick={() => skip.mutate()} disabled={skip.isPending || up.isPending}>
            {t("manual.skip")}
          </button>
        </div>
      )}
      <ErrorBox error={up.error || skip.error} />
    </div>
  );
}

export function ChatGptSetupCard({ book }: { book: Book }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["chatgpt-setup", book.id], queryFn: () => api.chatgptSetup(book.id) });
  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <div className="muted small">{t("common.loading")}</div>;
  const s = q.data;
  return (
    <div className="manual-task stack">
      <strong>{t("manual.setup_title")}</strong>
      <div className="small muted">{t("manual.setup_help")}</div>
      <ol className="stack small" style={{ margin: 0, paddingInlineStart: 20 }}>
        <li>
          {t("manual.setup_step1")} <code>{s.project_name}</code> <CopyButton text={s.project_name} label={t("manual.copy_name")} />
        </li>
        <li>
          {t("manual.setup_step2")} <CopyButton text={s.instructions} label={t("manual.copy_instructions")} primary />
          <details>
            <summary>{t("manual.show_prompt")}</summary>
            <pre>{s.instructions}</pre>
          </details>
        </li>
        <li>
          {t("manual.setup_step3")}
          {s.references.length === 0 ? (
            <div className="muted">{t("manual.no_refs")}</div>
          ) : (
            <div className="manual-refs">
              {s.references.map((r) => (
                <a key={r.url} className="manual-ref" href={url(r.url)} download target="_blank" rel="noopener noreferrer">
                  <img src={url(r.url)} alt={t(`manual.ref_kinds.${r.kind}`, { name: r.name })} loading="lazy" />
                  <span className="small">⬇ {t(`manual.ref_kinds.${r.kind}`, { name: r.name })}</span>
                </a>
              ))}
            </div>
          )}
        </li>
        <li>{t("manual.setup_step4")}</li>
      </ol>
    </div>
  );
}
