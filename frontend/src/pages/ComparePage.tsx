import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, links } from "../api/client";
import type { CompareOutput, CompareRun } from "../api/types";
import { ErrorBox, JobProgress } from "../components/ui";
import { useJob } from "../hooks/useJob";

export default function ComparePage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const runs = useQuery({ queryKey: ["compare-runs"], queryFn: api.compareRuns });
  const [picked, setPicked] = useState<string[]>(["mock"]);
  const [theme, setTheme] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const { job, running } = useJob(jobId, (j) => {
    qc.invalidateQueries({ queryKey: ["compare-runs"] });
    setOpen(String(j.result.run));
  });
  const start = useMutation({ mutationFn: () => api.startCompare(picked, theme || undefined), onSuccess: (j) => setJobId(j.id) });
  const run = useQuery({ queryKey: ["compare", open], queryFn: () => api.compareRun(open!), enabled: !!open });

  return (
    <div className="stack">
      <div className="row">
        <h1 style={{ margin: 0 }}>{t("compare.title")}</h1>
        <span className="spacer" />
        <Link to="/settings" className="btn small">
          {t("common.back")}
        </Link>
      </div>
      <p className="muted">{t("compare.help")}</p>
      <div className="card stack">
        <div className="row">
          {settings.data?.providers.image.map((p) => (
            <label key={p.name} className="checkbox">
              <input
                type="checkbox"
                disabled={!p.configured}
                checked={picked.includes(p.name)}
                onChange={(e) => setPicked(e.target.checked ? [...picked, p.name] : picked.filter((x) => x !== p.name))}
              />
              {p.name} <span className="muted small">({p.model})</span>
            </label>
          ))}
        </div>
        <input type="text" value={theme} onChange={(e) => setTheme(e.target.value)} placeholder={t("compare.theme_placeholder")} />
        <button className="btn primary" disabled={!picked.length || running} onClick={() => start.mutate()}>
          {t("compare.run")}
        </button>
        <ErrorBox error={start.error || runs.error} />
        {jobId && running && <JobProgress job={job} />}
      </div>
      <div className="card">
        <h3>{t("compare.runs")}</h3>
        {runs.data?.length === 0 && <p className="muted">{t("compare.no_runs")}</p>}
        <div className="row">
          {runs.data?.map((r) => (
            <button key={r.run} className={`btn small ${open === r.run ? "primary" : ""}`} onClick={() => setOpen(r.run)}>
              {r.run}
            </button>
          ))}
        </div>
      </div>
      {run.data && <RunView run={run.data} />}
    </div>
  );
}

function RunView({ run }: { run: CompareRun }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const score = useMutation({
    mutationFn: (a: { provider: string; index: number; key: string; value: number }) =>
      api.saveScore(run.run, a.provider, a.index, { [a.key]: a.value }),
    onSuccess: (data) => qc.setQueryData(["compare", run.run], data),
  });
  const providers = Array.isArray(run.providers) ? {} : run.providers;
  const names = Object.keys(providers);
  return (
    <div className="stack">
      <div className="card table-wrap">
        <h3>{t("compare.summary")}</h3>
        <table>
          <thead>
            <tr>
              {["provider", "model", "images", "errors", "avg_seconds", "total_cost_usd", "qa_redo_rate", "avg_clean_outlines", "avg_matches_sheet"].map((c) => (
                <th key={c}>{t(`compare.cols.${c}`)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {run.summary.map((r) => (
              <tr key={r.provider}>
                <td>{r.provider}</td>
                <td>{r.model}</td>
                <td>{r.images}</td>
                <td>{r.errors}</td>
                <td>{r.avg_seconds ?? "–"}</td>
                <td>{r.total_cost_usd}</td>
                <td>{r.qa_redo_rate ?? "–"}</td>
                <td>{r.avg_clean_outlines ?? "–"}</td>
                <td>{r.avg_matches_sheet ?? "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">{t("compare.no_winner")}</p>
      </div>
      <ErrorBox error={score.error} />
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              {names.map((n) => (
                <th key={n}>{n}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 10 }, (_, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                {names.map((n) => {
                  const o: CompareOutput | undefined = providers[n]?.outputs?.[i];
                  return (
                    <td key={n} style={{ minWidth: 180, verticalAlign: "top" }}>
                      {providers[n]?.error && i === 0 && <div className="alert error small">{providers[n].error}</div>}
                      {o?.file && (
                        <a href={links.compareFile(run.run, n, o.file.split("/").pop()!)} target="_blank" rel="noreferrer">
                          <div className="thumb">
                            <img src={links.compareFile(run.run, n, o.file.split("/").pop()!)} alt={`${n} ${i + 1}`} loading="lazy" />
                          </div>
                        </a>
                      )}
                      {o?.error && <div className="small" style={{ color: "var(--bad)" }}>{o.error}</div>}
                      {o && (
                        <div className="small muted">
                          {o.seconds}s · ${o.cost_usd} · QA {o.qa?.pass ? "✓" : "✕"}
                        </div>
                      )}
                      {o?.file &&
                        (["clean_outlines", "matches_sheet"] as const).map((k) => (
                          <div key={k} className="row small" style={{ gap: 4 }}>
                            <span>{t(`compare.score.${k}`)}</span>
                            <select
                              value={o.scores[k] ?? ""}
                              onChange={(e) => score.mutate({ provider: n, index: o.index, key: k, value: Number(e.target.value) })}
                              style={{ width: 64, padding: 4 }}
                            >
                              <option value="">–</option>
                              {[1, 2, 3, 4, 5].map((x) => (
                                <option key={x} value={x}>
                                  {x}
                                </option>
                              ))}
                            </select>
                          </div>
                        ))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
