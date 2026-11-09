import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import { isActive } from "../../api/types";
import { ErrorBox, JobProgress, Tag } from "../../components/ui";
import type { StepProps } from "../WizardPage";

export default function GenerateStep({ book, onNext }: StepProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["gen-status", book.id],
    queryFn: () => api.generationStatus(book.id),
    refetchInterval: (q) => {
      const s = q.state.data?.job?.status;
      return s === "waiting" ? 2000 : isActive(s) ? 1200 : false;
    },
  });
  const cost = useQuery({ queryKey: ["cost", book.id], queryFn: () => api.cost(book.id), refetchInterval: status.data?.job?.status === "running" ? 3000 : false });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["gen-status", book.id] });
    qc.invalidateQueries({ queryKey: ["book", book.id] });
    qc.invalidateQueries({ queryKey: ["cost", book.id] });
  };
  const start = useMutation({ mutationFn: () => api.generate(book.id), onSuccess: refresh });
  const cancel = useMutation({ mutationFn: () => api.cancelGeneration(book.id), onSuccess: refresh });
  const resume = useMutation({ mutationFn: (id: number) => api.retryJob(id), onSuccess: refresh });
  const job = status.data?.job;
  const running = isActive(job?.status);
  const waiting = job?.status === "waiting";
  const counts = status.data?.counts ?? {};
  const total = status.data?.total ?? 0;
  const done = (counts.generated ?? 0) + (counts.approved ?? 0) + (counts.failed ?? 0) + (counts.rejected ?? 0);
  const finished = total > 0 && !counts.queued && !counts.planned;
  const jobStatus = job?.status;
  useEffect(() => {
    if (jobStatus === "done" || jobStatus === "cancelled" || jobStatus === "failed") refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobStatus]);

  return (
    <div className="stack">
      <ErrorBox error={start.error || cancel.error || status.error} />
      <div className="card stack">
        <div className="row">
          <strong>{t("generate.pages_done", { done, total })}</strong>
          <span className="spacer" />
          {Object.entries(counts).map(([k, v]) => (
            <Tag key={k} kind={k}>
              {t(`status.${k}`)}: {v}
            </Tag>
          ))}
        </div>
        <div className="progress">
          <div style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
        </div>
        <div className="row small muted">
          <span>{t("generate.redos", { count: status.data?.redos ?? 0 })}</span>
          {typeof job?.result?.batch === "number" && <span>· {t("generate.batch", { n: job.result.batch, of: job.result.batches })}</span>}
          {cost.data && <span>· {t("generate.cost", { usd: cost.data.total_usd.toFixed(2) })}</span>}
        </div>
        <div className="row">
          {!running && !finished && (
            <button className="btn primary" onClick={() => start.mutate()} disabled={start.isPending}>
              {done > 0 ? t("generate.continue") : t("generate.start")}
            </button>
          )}
          {running && (
            <button className="btn danger" onClick={() => cancel.mutate()}>
              {t("generate.pause")}
            </button>
          )}
          {job && job.status === "cancelled" && !finished && (
            <button className="btn" onClick={() => resume.mutate(job.id)}>
              {t("generate.resume")}
            </button>
          )}
          {finished && !running && (
            <button className="btn primary" onClick={onNext}>
              {t("generate.to_review")}
            </button>
          )}
        </div>
        {waiting && <div className="alert warn">{t("generate.waiting_chatgpt")}</div>}
        {job?.status === "cancelled" && job.message && <div className="alert warn">{job.message}</div>}
        <div className="muted small">{t("generate.background_note")}</div>
      </div>
      {job && running && !waiting && <JobProgress job={job} label={t("generate.job_label")} />}
      {job?.status === "failed" && <JobProgress job={job} />}
    </div>
  );
}
