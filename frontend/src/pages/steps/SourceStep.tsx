import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import { ErrorBox, JobProgress } from "../../components/ui";
import { useJob, useStepJob } from "../../hooks/useJob";
import type { StepProps } from "../WizardPage";

type Mode = "url" | "url_pages" | "text";

export default function SourceStep({ book, onNext }: StepProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>(book.source_type === "url_pages" ? "url_pages" : book.source_type === "text" ? "text" : "url");
  const [link, setLink] = useState(book.source_url ?? "");
  const [text, setText] = useState(book.source_text ?? "");
  const [files, setFiles] = useState<File[]>([]);
  const [jobId, setJobId] = useStepJob(book.id, ["analyze_source"]);
  const { job, running } = useJob(jobId, () => onNext(), [["book", book.id]]);

  const submit = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      if (mode !== "text") fd.append("url", link.trim());
      fd.append("text", text.trim());
      if (mode === "url_pages") files.forEach((f) => fd.append("files", f));
      return api.submitSource(book.id, fd);
    },
    onSuccess: (r) => {
      setJobId(r.job.id);
      qc.invalidateQueries({ queryKey: ["book", book.id] });
    },
  });

  const fetchStatus = book.fetch?.status;
  const thin = fetchStatus === "thin" || fetchStatus === "failed" || fetchStatus === "blocked";
  const valid = mode === "text" ? text.trim().length > 0 : link.trim().length > 0 || text.trim().length > 0;

  return (
    <div className="stack">
      <div className="row" role="tablist">
        {(["url", "url_pages", "text"] as Mode[]).map((m) => (
          <button key={m} role="tab" aria-selected={mode === m} className={`btn small ${mode === m ? "primary" : ""}`} onClick={() => setMode(m)}>
            {t(`source.mode.${m}`)}
          </button>
        ))}
      </div>
      <div className="card">
        {mode !== "text" && (
          <div className="field">
            <label htmlFor="src-url">{t("source.url_label")}</label>
            <input id="src-url" type="url" inputMode="url" placeholder="https://" value={link} onChange={(e) => setLink(e.target.value)} />
            <div className="muted small">{t("source.url_hint")}</div>
          </div>
        )}
        {mode === "url_pages" && (
          <div className="field">
            <label htmlFor="src-files">{t("source.files_label")}</label>
            <input
              id="src-files"
              type="file"
              multiple
              accept="image/png,image/jpeg,image/webp,application/pdf"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            <div className="muted small">{t("source.files_hint")}</div>
          </div>
        )}
        <div className="field">
          <label htmlFor="src-text">{mode === "text" ? t("source.theme_label") : t("source.text_label")}</label>
          <textarea id="src-text" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("source.text_placeholder")} />
          <div className="muted small">{t("source.originality_note")}</div>
        </div>
        <button className="btn primary" disabled={!valid || submit.isPending || running} onClick={() => submit.mutate()}>
          {book.recipe ? t("source.reanalyze") : t("source.analyze")}
        </button>
      </div>
      <ErrorBox error={submit.error} />
      {thin && !running && (
        <div className="alert warn">
          <strong>{t(`source.fetch.${fetchStatus}`)}</strong> {t("source.fetch.fallback")}
          {book.fetch?.error && <div className="small muted">{book.fetch.error}</div>}
        </div>
      )}
      {fetchStatus === "ok" && !running && <div className="alert ok">{t("source.fetch.ok")}</div>}
      {jobId && <JobProgress job={job} label={t("source.analyzing")} />}
    </div>
  );
}
