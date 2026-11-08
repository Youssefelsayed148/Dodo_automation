import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import { Empty, ErrorBox, JobProgress } from "../../components/ui";
import { useJob, useStepJob } from "../../hooks/useJob";
import type { StepProps } from "../WizardPage";

export default function ThemeStep({ book }: StepProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const themes = book.themes ?? [];
  const chosen = themes.find((x) => x.chosen);
  const [title, setTitle] = useState(book.title);
  useEffect(() => setTitle(book.title), [book.title]);
  const [jobId, setJobId] = useStepJob(book.id, ["propose_themes"]);
  const { job, running } = useJob(jobId, undefined, [["book", book.id]]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["book", book.id] });

  const propose = useMutation({ mutationFn: () => api.proposeThemes(book.id), onSuccess: (j) => setJobId(j.id) });
  const choose = useMutation({ mutationFn: (id: number) => api.chooseTheme(book.id, id), onSuccess: refresh });
  const rename = useMutation({ mutationFn: () => api.rename(book.id, title), onSuccess: refresh });

  useEffect(() => {
    if (themes.length === 0 && !jobId && book.recipe && !propose.isPending) propose.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [themes.length, jobId]);

  return (
    <div className="stack">
      {jobId && running && <JobProgress job={job} label={t("theme.proposing")} />}
      <ErrorBox error={propose.error || choose.error || rename.error} />
      {themes.length === 0 && !running && (
        <Empty title={t("theme.empty")}>
          <button className="btn primary" onClick={() => propose.mutate()} disabled={!book.recipe}>
            {t("theme.propose")}
          </button>
        </Empty>
      )}
      <div className="grid">
        {themes.map((th) => (
          <div
            key={th.id}
            className={`card selectable ${th.chosen ? "selected" : ""}`}
            onClick={() => choose.mutate(th.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && choose.mutate(th.id)}
          >
            <h3>{th.title}</h3>
            <p className="muted" style={{ margin: 0 }}>
              {th.description}
            </p>
          </div>
        ))}
      </div>
      {themes.length > 0 && (
        <div className="row">
          <button className="btn" onClick={() => propose.mutate()} disabled={running || propose.isPending}>
            {t("theme.regenerate")}
          </button>
        </div>
      )}
      {chosen && (
        <div className="card">
          <label htmlFor="book-title">{t("theme.title_label")}</label>
          <div className="row">
            <input id="book-title" type="text" value={title} onChange={(e) => setTitle(e.target.value)} style={{ flex: 1, minWidth: 200 }} />
            <button className="btn" onClick={() => rename.mutate()} disabled={!title.trim() || title === book.title}>
              {t("common.save")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
