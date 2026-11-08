import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError, url } from "../api/client";
import type { Job } from "../api/types";

export function ErrorBox({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  let msg = t("errors.generic");
  if (error instanceof ApiError) msg = error.status === 0 ? t("errors.network") : error.message || msg;
  else if (error instanceof Error) msg = error.message;
  return (
    <div className="alert error" role="alert">
      {msg}
    </div>
  );
}

export function Tag({ kind, children }: { kind?: string; children: ReactNode }) {
  return <span className={`tag ${kind ?? ""}`}>{children}</span>;
}

export function StatusTag({ status }: { status: string }) {
  const { t } = useTranslation();
  return <Tag kind={status}>{t(`status.${status}`, { defaultValue: status })}</Tag>;
}

export function JobProgress({ job, label }: { job: Job | undefined; label?: string }) {
  const { t } = useTranslation();
  if (!job) return null;
  const pct = Math.round((job.progress || 0) * 100);
  return (
    <div className="card" aria-live="polite">
      <div className="row">
        <strong>{label ?? t(`jobs.${job.type}`, { defaultValue: job.type })}</strong>
        <StatusTag status={job.status} />
        <span className="spacer" />
        <span className="muted small">{pct}%</span>
      </div>
      <div className="progress" style={{ marginBlock: 8 }}>
        <div style={{ width: `${job.status === "done" ? 100 : pct}%` }} />
      </div>
      {job.message && <div className="muted small">{job.message}</div>}
      {job.status === "failed" && (
        <>
          <div className="alert error">{job.error || t("errors.generic")}</div>
          <button className="btn small" onClick={() => api.retryJob(job.id)}>
            {t("common.retry")}
          </button>
        </>
      )}
    </div>
  );
}

export function Modal({ onClose, children, title }: { onClose: () => void; children: ReactNode; title?: string }) {
  const { t } = useTranslation();
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ marginBlockEnd: 8 }}>
          {title && <h2 style={{ margin: 0 }}>{title}</h2>}
          <span className="spacer" />
          <button className="btn small" onClick={onClose}>
            {t("common.close")}
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Img({ src, alt, className }: { src: string | null | undefined; alt: string; className?: string }) {
  if (!src) return null;
  return <img src={url(src)} alt={alt} className={className} loading="lazy" />;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card center" style={{ padding: 32 }}>
      <div style={{ fontSize: "2.5rem" }} aria-hidden>
        🦤
      </div>
      <h3>{title}</h3>
      {children}
    </div>
  );
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
