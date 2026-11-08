import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { Lang } from "../../api/types";
import { ErrorBox, JobProgress, Tag } from "../../components/ui";
import { useJob, useStepJob } from "../../hooks/useJob";
import { pixelSize, TRIM_SIZES } from "../../lib/specs";
import type { StepProps } from "../WizardPage";

export default function SpecsStep({ book }: StepProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const isPreset = Object.keys(TRIM_SIZES).includes(book.trim_size);
  const [s, setS] = useState({
    page_count: book.page_count,
    trim: isPreset ? book.trim_size : "custom",
    custom: isPreset ? "7x10in" : book.trim_size,
    bleed: book.bleed,
    book_language: book.book_language as Lang,
    belongs_to: book.belongs_to,
    image_provider: book.image_provider,
  });
  useEffect(() => {
    setS((x) => ({ ...x, page_count: book.page_count, bleed: book.bleed, book_language: book.book_language }));
  }, [book.page_count, book.bleed, book.book_language]);
  const trim = s.trim === "custom" ? s.custom : s.trim;
  const px = pixelSize(trim, s.bleed);
  const pages = useQuery({ queryKey: ["pages", book.id], queryFn: () => api.pages(book.id) });
  const [jobId, setJobId] = useStepJob(book.id, ["plan_pages"]);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["book", book.id] });
    qc.invalidateQueries({ queryKey: ["pages", book.id] });
  };
  const { job, running } = useJob(jobId, refresh);

  const save = useMutation({
    mutationFn: () =>
      api.updateBook(book.id, {
        page_count: s.page_count,
        trim_size: trim,
        bleed: s.bleed,
        book_language: s.book_language,
        meta: { belongs_to: s.belongs_to, image_provider: s.image_provider },
      }),
    onSuccess: refresh,
  });
  const plan = useMutation({
    mutationFn: async () => {
      await save.mutateAsync();
      return api.plan(book.id);
    },
    onSuccess: (j) => setJobId(j.id),
  });
  const planned = pages.data ?? [];
  const dirty =
    s.page_count !== book.page_count || trim !== book.trim_size || s.bleed !== book.bleed || s.book_language !== book.book_language ||
    s.belongs_to !== book.belongs_to || s.image_provider !== book.image_provider;

  return (
    <div className="stack">
      <div className="card">
        <div className="grid">
          <div className="field">
            <label htmlFor="pc">{t("specs.page_count")}</label>
            <input id="pc" type="number" min={4} max={200} value={s.page_count} onChange={(e) => setS({ ...s, page_count: Number(e.target.value) })} />
          </div>
          <div className="field">
            <label htmlFor="trim">{t("specs.trim")}</label>
            <select id="trim" value={s.trim} onChange={(e) => setS({ ...s, trim: e.target.value })}>
              {Object.keys(TRIM_SIZES).map((k) => (
                <option key={k} value={k}>
                  {t(`specs.trims.${k}`, { defaultValue: k })}
                </option>
              ))}
              <option value="custom">{t("specs.custom")}</option>
            </select>
            {s.trim === "custom" && (
              <input type="text" value={s.custom} onChange={(e) => setS({ ...s, custom: e.target.value })} placeholder="7x10in / 200x250mm" style={{ marginBlockStart: 6 }} />
            )}
          </div>
          <div className="field">
            <label htmlFor="blang">{t("specs.book_language")}</label>
            <select id="blang" value={s.book_language} onChange={(e) => setS({ ...s, book_language: e.target.value as Lang })}>
              <option value="en">{t("lang.en")}</option>
              <option value="ar">{t("lang.ar")}</option>
            </select>
            <div className="muted small">{t("specs.book_language_help")}</div>
          </div>
          <div className="field">
            <label htmlFor="prov">{t("specs.image_provider")}</label>
            <select id="prov" value={s.image_provider} onChange={(e) => setS({ ...s, image_provider: e.target.value })}>
              <option value="">{t("specs.provider_default")}</option>
              {settings.data?.providers.image.map((p) => (
                <option key={p.name} value={p.name} disabled={!p.configured}>
                  {p.name} ({p.model}){p.configured ? "" : ` – ${t("settings.not_configured")}`}
                </option>
              ))}
            </select>
          </div>
        </div>
        <label className="checkbox">
          <input type="checkbox" checked={s.bleed} onChange={(e) => setS({ ...s, bleed: e.target.checked })} />
          {t("specs.bleed")}
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={s.belongs_to} onChange={(e) => setS({ ...s, belongs_to: e.target.checked })} />
          {t("specs.belongs_to")}
        </label>
        <div className="alert" style={{ marginBlockStart: 12 }}>
          {px ? t("specs.pixel_size", { w: px[0], h: px[1] }) : <span className="tag bad">{t("specs.invalid_trim")}</span>}
        </div>
        <ErrorBox error={save.error || plan.error} />
        <div className="row">
          <button className="btn" onClick={() => save.mutate()} disabled={!dirty || !px || save.isPending}>
            {t("common.save")}
          </button>
          <button className="btn primary" onClick={() => plan.mutate()} disabled={!px || running || plan.isPending}>
            {planned.length ? t("specs.replan") : t("specs.plan")}
          </button>
        </div>
        {planned.length > 0 && <div className="muted small">{t("specs.replan_warning")}</div>}
      </div>
      {jobId && running && <JobProgress job={job} label={t("specs.planning")} />}
      {planned.length > 0 && (
        <div className="card">
          <h3>{t("specs.plan_title", { count: planned.length })}</h3>
          {book.content_check && !book.content_check.ok && (
            <div className="alert warn">{book.content_check.issues.join("\n")}</div>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>{t("specs.col_type")}</th>
                  <th>{t("specs.col_description")}</th>
                </tr>
              </thead>
              <tbody>
                {planned.map((p) => (
                  <tr key={p.id}>
                    <td>{p.index}</td>
                    <td>
                      <Tag kind={p.is_image ? "" : "ok"}>{t(`page_types.${p.type}`)}</Tag>
                    </td>
                    <td className="small">
                      {p.description}
                      {p.text_content?.question && <div className="muted">❓ {p.text_content.question}</div>}
                      {p.text_content?.words && <div className="muted">🔤 {p.text_content.words.join(", ")}</div>}
                      {p.text_content?.text && <div className="muted">✏️ {p.text_content.text}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
