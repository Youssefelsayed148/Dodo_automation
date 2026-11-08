import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { Page } from "../../api/types";
import { ErrorBox, Img, JobProgress, Modal, StatusTag, Tag } from "../../components/ui";
import { useJob } from "../../hooks/useJob";
import type { StepProps } from "../WizardPage";

export default function ReviewStep({ book }: StepProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const pages = useQuery({ queryKey: ["pages", book.id], queryFn: () => api.pages(book.id) });
  const [detail, setDetail] = useState<Page | null>(null);
  const [note, setNote] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["pages", book.id] });
    qc.invalidateQueries({ queryKey: ["book", book.id] });
  };
  const { job, running } = useJob(jobId, refresh);
  const toggle = useMutation({
    mutationFn: (p: Page) => api.review(book.id, p.id, p.status === "rejected" ? "generated" : "rejected"),
    onSuccess: refresh,
  });
  const approve = useMutation({ mutationFn: (p: Page) => api.review(book.id, p.id, "approved"), onSuccess: refresh });
  const approveAll = useMutation({ mutationFn: () => api.approveAll(book.id, true), onSuccess: refresh });
  const redo = useMutation({
    mutationFn: () => api.redo(book.id, note || undefined),
    onSuccess: (r) => {
      setJobId(r.job.id);
      setNote("");
      refresh();
    },
  });

  const list = useMemo(
    () => [...(pages.data ?? [])].sort((a, b) => Number(b.status === "failed") - Number(a.status === "failed") || a.index - b.index),
    [pages.data],
  );
  const failed = list.filter((p) => p.status === "failed").length;
  const rejected = list.filter((p) => p.status === "rejected").length;
  const approved = list.filter((p) => p.status === "approved").length;

  return (
    <div className="stack">
      <ErrorBox error={pages.error || toggle.error || approveAll.error || redo.error} />
      {failed > 0 && <div className="alert warn">{t("review.failed_banner", { count: failed })}</div>}
      <div className="card row">
        <span>{t("review.summary", { approved, total: list.length })}</span>
        <span className="spacer" />
        <button className="btn" onClick={() => approveAll.mutate()} disabled={approveAll.isPending}>
          {t("review.approve_all")}
        </button>
      </div>
      {rejected > 0 && (
        <div className="card row">
          <input type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("review.note_placeholder")} style={{ flex: 1, minWidth: 200 }} />
          <button className="btn primary" onClick={() => redo.mutate()} disabled={running || redo.isPending}>
            {t("review.redo", { count: rejected })}
          </button>
        </div>
      )}
      {jobId && running && <JobProgress job={job} label={t("review.redoing")} />}
      <p className="muted small">{t("review.tap_help")}</p>
      <div className="grid-sm">
        {list.map((p) => (
          <div key={p.id}>
            <div className={`thumb ${p.status}`} onClick={() => p.image_url && toggle.mutate(p)} role="button" aria-pressed={p.status === "rejected"} aria-label={t("review.page_n", { n: p.index })}>
              {p.thumb_url ? <Img src={p.thumb_url} alt={t("review.page_n", { n: p.index })} /> : <div className="center muted small" style={{ paddingBlockStart: "40%" }}>{t(`status.${p.status}`)}</div>}
              <span className="badge">
                <StatusTag status={p.status} />
              </span>
              <span className="idx">{p.index}</span>
              {p.status === "rejected" && <span className="x">✕</span>}
            </div>
            <div className="row small" style={{ marginBlockStart: 4 }}>
              <span className="muted">{t(`page_types.${p.type}`)}</span>
              <span className="spacer" />
              <button className="btn small ghost" onClick={() => setDetail(p)}>
                {t("review.details")}
              </button>
            </div>
          </div>
        ))}
      </div>
      {detail && (
        <Modal onClose={() => setDetail(null)} title={t("review.page_n", { n: detail.index })}>
          <div className="grid">
            <div className="thumb" style={{ cursor: "default" }}>
              <Img src={detail.image_url} alt={t("review.page_n", { n: detail.index })} />
            </div>
            <div className="stack small">
              <div className="row">
                <StatusTag status={detail.status} />
                <Tag>{t(`page_types.${detail.type}`)}</Tag>
                <span className="muted">{t("review.attempts", { count: detail.attempts })}</span>
              </div>
              <div>
                <strong>{t("review.description")}</strong>
                <div>{detail.description}</div>
              </div>
              {detail.prompt && (
                <div>
                  <strong>{t("review.prompt")}</strong>
                  <pre>{detail.prompt}</pre>
                </div>
              )}
              <div>
                <strong>{t("review.qa")}</strong>
                {detail.qa?.pass === true && <div className="tag ok">{t("review.qa_pass")}</div>}
                {detail.qa?.pass === false && (
                  <ul>
                    {(detail.qa.issues ?? []).map((i: string) => (
                      <li key={i}>{i}</li>
                    ))}
                    {detail.qa.error && <li>{detail.qa.error}</li>}
                  </ul>
                )}
                {detail.qa?.metrics && <pre>{JSON.stringify(detail.qa.metrics, null, 1)}</pre>}
              </div>
              <div className="row">
                <button className="btn small primary" onClick={() => { approve.mutate(detail); setDetail(null); }} disabled={!detail.image_url}>
                  {t("review.approve")}
                </button>
                <button className="btn small" onClick={() => { toggle.mutate(detail); setDetail(null); }} disabled={!detail.image_url}>
                  {detail.status === "rejected" ? t("review.unreject") : t("review.reject")}
                </button>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
