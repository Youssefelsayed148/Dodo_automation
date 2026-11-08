import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, links } from "../../api/client";
import type { Book } from "../../api/types";
import { copyText, ErrorBox, Tag } from "../../components/ui";

export default function ExportPromptsPanel({ book, onClose }: { book: Book; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [batchSize, setBatchSize] = useState<number | undefined>(undefined);
  const [copied, setCopied] = useState<string | null>(null);
  const [done, setDone] = useState<number[]>(book.prompt_batches_done ?? []);
  const [importText, setImportText] = useState("");
  const data = useQuery({ queryKey: ["prompts", book.id, batchSize], queryFn: () => api.prompts(book.id, batchSize) });
  const preview = useMutation({ mutationFn: () => api.importPlan(book.id, importText, false) });
  const apply = useMutation({
    mutationFn: () => api.importPlan(book.id, importText, true),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pages", book.id] });
      qc.invalidateQueries({ queryKey: ["book", book.id] });
      qc.invalidateQueries({ queryKey: ["prompts", book.id] });
    },
  });
  const copy = async (key: string, text: string) => {
    if (await copyText(text)) {
      setCopied(key);
      setTimeout(() => setCopied(null), 1500);
    }
  };
  const toggleDone = (n: number) => {
    const next = done.includes(n) ? done.filter((x) => x !== n) : [...done, n];
    setDone(next);
    api.promptsDone(book.id, next).catch(() => undefined);
  };

  return (
    <aside className="drawer" aria-label={t("prompts.title")}>
      <div className="row" style={{ marginBlockEnd: 8 }}>
        <h2 style={{ margin: 0 }}>{t("prompts.title")}</h2>
        <span className="spacer" />
        <button className="btn small" onClick={onClose}>
          {t("common.close")}
        </button>
      </div>
      <p className="muted small">{t("prompts.help")}</p>
      <ErrorBox error={data.error} />
      {data.data && (
        <div className="stack">
          <div className="card">
            <div className="row">
              <h3 style={{ margin: 0 }}>{t("prompts.planning")}</h3>
              <span className="spacer" />
              <button className="btn small" onClick={() => copy("plan", data.data.planning_prompt)}>
                {copied === "plan" ? t("common.copied") : t("common.copy")}
              </button>
              <a className="btn small" href={links.promptsMd(book.id, batchSize)}>
                .md
              </a>
            </div>
            <pre style={{ marginBlockStart: 8 }}>{data.data.planning_prompt}</pre>
          </div>
          <div className="card">
            <div className="row">
              <h3 style={{ margin: 0 }}>{t("prompts.pack")}</h3>
              <span className="spacer" />
              <select value={batchSize ?? data.data.batch_size} onChange={(e) => setBatchSize(Number(e.target.value))} style={{ width: 90 }} aria-label={t("prompts.batch_size")}>
                <option value={5}>5</option>
                <option value={10}>10</option>
              </select>
            </div>
            {data.data.batches.length === 0 && <p className="muted small">{t("prompts.no_batches")}</p>}
            {data.data.batches.map((b) => (
              <div key={b.batch} style={{ marginBlockStart: 10 }}>
                <div className="row">
                  <label className="checkbox" style={{ margin: 0 }}>
                    <input type="checkbox" checked={done.includes(b.batch)} onChange={() => toggleDone(b.batch)} />
                    {t("prompts.batch_n", { n: b.batch, pages: b.page_indexes.join(", ") })}
                  </label>
                  <span className="spacer" />
                  <button className="btn small" onClick={() => copy(`b${b.batch}`, b.text)}>
                    {copied === `b${b.batch}` ? t("common.copied") : t("common.copy")}
                  </button>
                </div>
                <pre style={{ marginBlockStart: 6, maxHeight: 160 }}>{b.text}</pre>
              </div>
            ))}
          </div>
          <div className="card stack">
            <h3 style={{ margin: 0 }}>{t("prompts.import")}</h3>
            <textarea value={importText} onChange={(e) => setImportText(e.target.value)} placeholder={t("prompts.import_placeholder")} style={{ minHeight: 140 }} />
            <div className="row">
              <button className="btn small" onClick={() => preview.mutate()} disabled={!importText.trim()}>
                {t("prompts.preview")}
              </button>
              <button className="btn small primary" onClick={() => window.confirm(t("prompts.apply_confirm")) && apply.mutate()} disabled={!importText.trim()}>
                {t("prompts.apply")}
              </button>
            </div>
            <ErrorBox error={preview.error || apply.error} />
            {apply.isSuccess && <div className="alert ok">{t("prompts.applied")}</div>}
            {preview.data && (
              <div className="table-wrap">
                <div className="small">{t("prompts.changed", { count: preview.data.diff.changed })}</div>
                <table>
                  <tbody>
                    {preview.data.diff.rows.map((r) => (
                      <tr key={r.n}>
                        <td>{r.n}</td>
                        <td>
                          <Tag kind={r.change === "same" ? "" : r.change === "removed" ? "bad" : "warn"}>{t(`prompts.change.${r.change}`)}</Tag>
                        </td>
                        <td className="small">{r.new?.description ?? r.old?.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
