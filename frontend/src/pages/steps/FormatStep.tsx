import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { FormatOption } from "../../api/types";
import { Empty, ErrorBox, JobProgress, Tag } from "../../components/ui";
import { useJob, useStepJob } from "../../hooks/useJob";
import type { Block } from "../../lib/mix";
import type { StepProps } from "../WizardPage";
import MixEditor from "./MixEditor";

export default function FormatStep({ book }: StepProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const formats = book.formats ?? [];
  const chosen = formats.find((f) => f.chosen);
  const [editing, setEditing] = useState<Record<number, Block[]>>({});
  const [hybridText, setHybridText] = useState("");
  const [jobId, setJobId] = useStepJob(book.id, ["propose_formats"]);
  const { job, running } = useJob(jobId, undefined, [["book", book.id]]);
  const preview = useQuery({ queryKey: ["plan-preview", book.id, book.format_id, book.page_count], queryFn: () => api.planPreview(book.id), enabled: !!book.format_id });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["book", book.id] });
    qc.invalidateQueries({ queryKey: ["plan-preview", book.id] });
  };

  const propose = useMutation({ mutationFn: () => api.proposeFormats(book.id), onSuccess: (j) => setJobId(j.id) });
  const hybrid = useMutation({ mutationFn: () => api.hybrid(book.id, hybridText), onSuccess: (j) => { setJobId(j.id); setHybridText(""); } });
  const choose = useMutation({
    mutationFn: (f: FormatOption) => api.chooseFormat(book.id, f.id, editing[f.id]),
    onSuccess: refresh,
  });

  useEffect(() => {
    if (formats.length === 0 && !jobId && book.theme_id && !propose.isPending) propose.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formats.length, jobId]);

  const counts: Record<string, number> = {};
  (preview.data?.slots ?? []).forEach((s) => (counts[s] = (counts[s] ?? 0) + 1));

  return (
    <div className="stack">
      {jobId && running && <JobProgress job={job} label={t("format.proposing")} />}
      <ErrorBox error={propose.error || hybrid.error || choose.error} />
      {formats.length === 0 && !running && (
        <Empty title={t("format.empty")}>
          <button className="btn primary" onClick={() => propose.mutate()}>
            {t("format.propose")}
          </button>
        </Empty>
      )}
      <div className="grid">
        {formats.map((f) => {
          const blocks = editing[f.id] ?? f.blocks;
          const isEditing = !!editing[f.id];
          return (
            <div key={f.id} className={`card ${f.chosen ? "selected" : ""}`}>
              <h3>{f.name}</h3>
              <p className="muted small">{f.description}</p>
              {isEditing ? (
                <MixEditor blocks={blocks} onChange={(b) => setEditing({ ...editing, [f.id]: b })} />
              ) : (
                <div className="row">
                  {blocks.map((b) => (
                    <Tag key={b.type}>
                      {t(`page_types.${b.type}`)} {b.share}%
                    </Tag>
                  ))}
                </div>
              )}
              <div className="row" style={{ marginBlockStart: 10 }}>
                <button className="btn small primary" onClick={() => choose.mutate(f)} disabled={choose.isPending}>
                  {f.chosen && !isEditing ? t("format.chosen") : t("format.choose")}
                </button>
                {!isEditing && (
                  <button className="btn small" onClick={() => setEditing({ ...editing, [f.id]: f.blocks.map((b) => ({ ...b })) })}>
                    {t("format.edit_mix")}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {formats.length > 0 && (
        <div className="card">
          <label htmlFor="hybrid">{t("format.hybrid_label")}</label>
          <div className="row">
            <input id="hybrid" type="text" value={hybridText} onChange={(e) => setHybridText(e.target.value)} placeholder={t("format.hybrid_placeholder")} style={{ flex: 1, minWidth: 200 }} />
            <button className="btn" disabled={!hybridText.trim() || running} onClick={() => hybrid.mutate()}>
              {t("format.hybrid_button")}
            </button>
            <button className="btn" disabled={running} onClick={() => propose.mutate()}>
              {t("format.regenerate")}
            </button>
          </div>
        </div>
      )}
      {chosen && preview.data && (
        <div className="card">
          <h3>{t("format.preview_title", { count: preview.data.slots.length })}</h3>
          <div className="row">
            {Object.entries(counts).map(([type, n]) => (
              <Tag key={type}>
                {t(`page_types.${type}`)} × {n}
              </Tag>
            ))}
          </div>
          <ol className="small muted" style={{ columns: 2, marginBlockEnd: 0 }}>
            {preview.data.slots.map((s, i) => (
              <li key={i}>{t(`page_types.${s}`)}</li>
            ))}
          </ol>
          <div className="muted small">{t("format.preview_note")}</div>
        </div>
      )}
    </div>
  );
}
