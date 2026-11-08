import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, links } from "../../api/client";
import { ErrorBox, JobProgress, Tag } from "../../components/ui";
import { useJob, useStepJob } from "../../hooks/useJob";
import type { StepProps } from "../WizardPage";

const TEMPLATES = ["classic", "framed", "band"];

export default function ExportStep({ book }: StepProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const drive = useQuery({ queryKey: ["drive"], queryFn: api.driveStatus });
  const files = useQuery({ queryKey: ["export-files", book.id], queryFn: () => api.exportFiles(book.id) });
  const pages = useQuery({ queryKey: ["pages", book.id], queryFn: () => api.pages(book.id) });
  const cost = useQuery({ queryKey: ["cost", book.id], queryFn: () => api.cost(book.id) });
  const [useDrive, setUseDrive] = useState(false);
  const [folder, setFolder] = useState(book.title);
  const [cover, setCover] = useState({ template: book.cover.template ?? "classic", page_id: book.cover.page_id ?? 0, subtitle: book.cover.subtitle ?? "" });
  const [bust, setBust] = useState(Date.now());
  useEffect(() => setFolder(book.title), [book.title]);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["export-files", book.id] });
    qc.invalidateQueries({ queryKey: ["book", book.id] });
    setBust(Date.now());
  };
  const [jobId, setJobId] = useStepJob(book.id, ["export_book"]);
  const exp = useJob(jobId, refresh);
  const [artJob, setArtJob] = useStepJob(book.id, ["cover_art"]);
  const art = useJob(artJob, refresh);

  const run = useMutation({ mutationFn: () => api.exportBook(book.id, { drive: useDrive, folder_name: folder }), onSuccess: (j) => setJobId(j.id) });
  const saveCover = useMutation({
    mutationFn: () => api.saveCover(book.id, { template: cover.template, subtitle: cover.subtitle, ...(cover.page_id ? { page_id: cover.page_id } : {}) }),
    onSuccess: refresh,
  });
  const genArt = useMutation({ mutationFn: () => api.coverArt(book.id), onSuccess: (j) => setArtJob(j.id) });
  const coverPages = (pages.data ?? []).filter((p) => p.is_image && p.image_url);
  const result = exp.job?.status === "done" ? (exp.job.result as any) : null;
  const driveLink = result?.drive?.link ?? book.drive?.link;

  return (
    <div className="stack">
      <div className="card stack">
        <h3>{t("export.cover")}</h3>
        <div className="grid">
          <div className="stack">
            <div className="field">
              <label htmlFor="tpl">{t("export.template")}</label>
              <select id="tpl" value={cover.template} onChange={(e) => setCover({ ...cover, template: e.target.value })}>
                {TEMPLATES.map((x) => (
                  <option key={x} value={x}>
                    {t(`export.templates.${x}`)}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="cpage">{t("export.cover_art")}</label>
              <select id="cpage" value={cover.page_id} onChange={(e) => setCover({ ...cover, page_id: Number(e.target.value) })}>
                <option value={0}>{book.cover.art_url ? t("export.generated_art") : t("export.first_scene")}</option>
                {coverPages.map((p) => (
                  <option key={p.id} value={p.id}>
                    {t("review.page_n", { n: p.index })} – {p.description.slice(0, 40)}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="sub">{t("export.subtitle")}</label>
              <input id="sub" type="text" value={cover.subtitle} onChange={(e) => setCover({ ...cover, subtitle: e.target.value })} />
            </div>
            <div className="row">
              <button className="btn small primary" onClick={() => saveCover.mutate()}>
                {t("export.save_cover")}
              </button>
              <button className="btn small" onClick={() => genArt.mutate()} disabled={art.running}>
                {t("export.generate_art")}
              </button>
            </div>
            {artJob && art.running && <JobProgress job={art.job} />}
            <ErrorBox error={saveCover.error || genArt.error} />
          </div>
          <div className="thumb" style={{ cursor: "default", maxWidth: 300 }}>
            <img src={links.coverPreview(book.id, bust)} alt={t("export.cover_preview")} onError={(e) => ((e.target as HTMLImageElement).style.display = "none")} />
          </div>
        </div>
      </div>

      <div className="card stack">
        <h3>{t("export.files_title")}</h3>
        <label className="checkbox">
          <input type="checkbox" checked={useDrive} disabled={!drive.data?.connected} onChange={(e) => setUseDrive(e.target.checked)} />
          {t("export.drive_toggle")}
        </label>
        {!drive.data?.connected && (
          <div className="alert">
            {drive.data?.configured ? t("export.drive_connect_hint") : t("export.drive_setup_hint")} <Link to="/settings">{t("nav.settings")}</Link>
          </div>
        )}
        {useDrive && (
          <div className="field">
            <label htmlFor="folder">{t("export.folder_name")}</label>
            <input id="folder" type="text" value={folder} onChange={(e) => setFolder(e.target.value)} />
            <div className="muted small">{t("export.folder_hint")}</div>
          </div>
        )}
        <div className="row">
          <button className="btn primary" onClick={() => run.mutate()} disabled={exp.running || run.isPending}>
            {t("export.run")}
          </button>
          <a className="btn" href={links.backup(book.id)}>
            {t("export.backup")}
          </a>
        </div>
        <ErrorBox error={run.error} />
        {jobId && <JobProgress job={exp.job} label={t("export.running")} />}
        {driveLink && (
          <div className="alert ok">
            {t("export.drive_done")}{" "}
            <a href={driveLink} target="_blank" rel="noreferrer">
              {result?.drive?.folder_name ?? book.drive?.folder_name}
            </a>
          </div>
        )}
        {files.data && files.data.files.length > 0 && (
          <div>
            <div className="row">
              <a className="btn small" href={links.exportFile(book.id, "interior.pdf")} target="_blank" rel="noreferrer">
                interior.pdf
              </a>
              <a className="btn small" href={links.exportFile(book.id, "cover.pdf")} target="_blank" rel="noreferrer">
                cover.pdf
              </a>
              <a className="btn small" href={links.exportFile(book.id, "book-settings.json")} target="_blank" rel="noreferrer">
                book-settings.json
              </a>
            </div>
            <details style={{ marginBlockStart: 8 }}>
              <summary className="small">{t("export.all_files", { count: files.data.files.length })}</summary>
              <ul className="small muted">
                {files.data.files.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </details>
            <iframe title={t("export.pdf_preview")} src={links.exportFile(book.id, "interior.pdf")} style={{ width: "100%", height: 480, border: "1px solid var(--border)", borderRadius: 12, marginBlockStart: 8 }} />
          </div>
        )}
      </div>

      {cost.data && (
        <div className="card">
          <h3>{t("cost.title")}</h3>
          <div className="row">
            <Tag>{t("cost.total", { usd: cost.data.total_usd.toFixed(2) })}</Tag>
            <Tag>{t("cost.per_page", { usd: cost.data.avg_per_image_page.toFixed(3) })}</Tag>
            <Tag>{t("cost.redos", { count: cost.data.total_redos })}</Tag>
            {cost.data.ceiling_usd > 0 && <Tag kind="warn">{t("cost.ceiling", { usd: cost.data.ceiling_usd })}</Tag>}
          </div>
          <details style={{ marginBlockStart: 8 }}>
            <summary className="small">{t("cost.per_page_table")}</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>{t("specs.col_type")}</th>
                    <th>{t("cost.images")}</th>
                    <th>{t("cost.redone")}</th>
                    <th>USD</th>
                  </tr>
                </thead>
                <tbody>
                  {cost.data.pages.map((p) => (
                    <tr key={p.page_id}>
                      <td>{p.index}</td>
                      <td>{t(`page_types.${p.type}`)}</td>
                      <td>{p.images}</td>
                      <td>{p.redone}</td>
                      <td>{p.cost.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
