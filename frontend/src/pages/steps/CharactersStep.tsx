import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { Book, Character } from "../../api/types";
import { ChatGptSetupCard, useManualMode } from "../../components/ManualTasks";
import { Empty, ErrorBox, Img, JobProgress, Modal, StatusTag, Tag } from "../../components/ui";
import { useJob, useStepJob } from "../../hooks/useJob";
import type { StepProps } from "../WizardPage";

export default function CharactersStep({ book }: StepProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const data = useQuery({ queryKey: ["characters", book.id], queryFn: () => api.characters(book.id) });
  const [count, setCount] = useState(1);
  const [libOpen, setLibOpen] = useState(false);
  const [briefJob, setBriefJob] = useStepJob(book.id, ["character_briefs"]);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["characters", book.id] });
    qc.invalidateQueries({ queryKey: ["book", book.id] });
  };
  const briefs = useJob(briefJob, refresh);
  const create = useMutation({ mutationFn: () => api.briefs(book.id, count), onSuccess: (j) => setBriefJob(j.id) });
  const chars = data.data?.characters ?? [];
  const gates = data.data?.gates;
  const manual = useManualMode();
  const [setupOpen, setSetupOpen] = useState(false);

  return (
    <div className="stack">
      <ErrorBox error={data.error || create.error} />
      {manual && (
        <div className="card">
          <div className="row">
            <strong>{t("manual.setup_title")}</strong>
            <span className="spacer" />
            <button className="btn small" onClick={() => setSetupOpen(!setupOpen)}>
              {setupOpen ? t("common.hide") : t("manual.setup_open")}
            </button>
          </div>
          {setupOpen && <ChatGptSetupCard book={book} />}
        </div>
      )}
      <StyleAnchor book={book} rules={data.data?.style_anchor.rules ?? ""} refUrl={data.data?.style_anchor.reference_url ?? null} />
      {briefJob && briefs.running && <JobProgress job={briefs.job} label={t("characters.creating")} />}
      {chars.length === 0 && !briefs.running && (
        <Empty title={t("characters.empty")}>
          <p className="muted">{t("characters.empty_help")}</p>
        </Empty>
      )}
      <div className="card row">
        <label htmlFor="ccount" style={{ margin: 0 }}>
          {t("characters.how_many")}
        </label>
        <select id="ccount" value={count} onChange={(e) => setCount(Number(e.target.value))} style={{ width: 80 }}>
          {[1, 2, 3, 4].map((n) => (
            <option key={n}>{n}</option>
          ))}
        </select>
        <button className="btn primary" onClick={() => create.mutate()} disabled={briefs.running || create.isPending}>
          {t("characters.create_briefs")}
        </button>
        <button className="btn" onClick={() => setLibOpen(true)}>
          {t("characters.from_library")}
        </button>
      </div>
      {chars.map((c) => (
        <CharacterCard key={c.id} book={book} c={c} onChange={refresh} />
      ))}
      {gates && <SampleSection book={book} ready={gates.characters_ok} sampleOk={gates.sample_ok} onChange={refresh} />}
      {libOpen && <LibraryPicker book={book} onClose={() => setLibOpen(false)} onPicked={refresh} />}
    </div>
  );
}

function StyleAnchor({ book, rules, refUrl }: { book: Book; rules: string; refUrl: string | null }) {
  const { t } = useTranslation();
  const [text, setText] = useState(rules);
  const [open, setOpen] = useState(false);
  useEffect(() => setText(rules), [rules]);
  const save = useMutation({ mutationFn: () => api.saveStyle(book.id, text) });
  return (
    <div className="card">
      <div className="row">
        <strong>{t("characters.style_anchor")}</strong>
        <span className="muted small">{t("characters.style_anchor_help")}</span>
        <span className="spacer" />
        <button className="btn small" onClick={() => setOpen(!open)}>
          {open ? t("common.hide") : t("common.edit")}
        </button>
      </div>
      {open && (
        <div className="stack" style={{ marginBlockStart: 10 }}>
          {refUrl && (
            <div className="thumb square" style={{ maxWidth: 140 }}>
              <Img src={refUrl} alt={t("characters.style_reference")} />
            </div>
          )}
          <textarea value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row">
            <button className="btn small primary" onClick={() => save.mutate()} disabled={save.isPending}>
              {t("common.save")}
            </button>
            {save.isSuccess && <span className="muted small">{t("common.saved")}</span>}
          </div>
          <ErrorBox error={save.error} />
        </div>
      )}
    </div>
  );
}

function CharacterCard({ book, c, onChange }: { book: Book; c: Character; onChange: () => void }) {
  const { t } = useTranslation();
  const [jobId, setJobId] = useState<number | null>(null);
  const { job, running } = useJob(jobId, onChange);
  const [instruction, setInstruction] = useState("");
  const [fields, setFields] = useState({ name: c.name, species: c.species, personality: c.personality, proportions: c.proportions, signature_feature: c.signature_feature, outfit: c.outfit });
  const [editBrief, setEditBrief] = useState(false);
  const [zoom, setZoom] = useState<string | null>(null);
  const start = (p: Promise<{ id: number }>) => p.then((j) => setJobId(j.id));
  const act = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: onChange });

  const cands = c.assets.filter((a) => a.kind === "candidate");
  const selected = cands.find((a) => a.selected);
  const sheet = c.assets.filter((a) => a.kind === "sheet" || a.kind === "expression");
  const tests = c.assets.filter((a) => a.kind === "test_scene");
  const cons = c.consistency;

  return (
    <div className="card stack">
      <div className="row">
        <h3 style={{ margin: 0 }}>{c.name}</h3>
        <StatusTag status={c.status} />
        {c.in_library && <Tag kind="ok">{t("characters.in_library")}</Tag>}
        <span className="spacer" />
        <button className="btn small" onClick={() => setEditBrief(!editBrief)}>
          {editBrief ? t("common.hide") : t("characters.edit_brief")}
        </button>
      </div>
      {!editBrief ? (
        <div className="small">
          <div>
            <strong>{t("characters.species")}:</strong> {c.species} · <strong>{t("characters.signature")}:</strong> {c.signature_feature}
          </div>
          <div className="muted">
            {c.proportions} · {c.personality} {c.outfit && `· ${c.outfit}`}
          </div>
        </div>
      ) : (
        <div className="grid">
          {(Object.keys(fields) as (keyof typeof fields)[]).map((k) => (
            <div className="field" key={k}>
              <label htmlFor={`${c.id}-${k}`}>{t(`characters.fields.${k}`)}</label>
              <input id={`${c.id}-${k}`} type="text" value={fields[k]} onChange={(e) => setFields({ ...fields, [k]: e.target.value })} />
            </div>
          ))}
          <button className="btn small primary" onClick={() => act.mutate(() => api.updateCharacter(book.id, c.id, fields))}>
            {t("common.save")}
          </button>
        </div>
      )}

      {jobId && running && <JobProgress job={job} />}
      {job?.status === "failed" && <JobProgress job={job} />}
      <ErrorBox error={act.error} />

      {/* 1. candidates */}
      <section>
        <div className="row">
          <h4 style={{ margin: 0 }}>1. {t("characters.candidates")}</h4>
          <span className="spacer" />
          <button className="btn small" disabled={running} onClick={() => start(api.candidates(book.id, c.id))}>
            {cands.length ? t("characters.more_candidates") : t("characters.generate_candidates")}
          </button>
        </div>
        {cands.length > 0 && (
          <div className="grid-sm" style={{ marginBlockStart: 8 }}>
            {cands.map((a) => (
              <div key={a.id} className={`thumb square ${a.selected ? "selected" : ""}`} onClick={() => act.mutate(() => api.select(book.id, c.id, a.id))} title={a.meta.instruction ?? ""}>
                <Img src={a.thumb_url} alt={c.name} />
                <span className="idx">v{a.meta.version}</span>
                {a.selected && <span className="badge tag ok">{t("characters.picked")}</span>}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 2. lock and edit */}
      {selected && (
        <section>
          <h4>2. {t("characters.lock_edit")}</h4>
          <div className="row">
            <input type="text" value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder={t("characters.edit_placeholder")} style={{ flex: 1, minWidth: 200 }} />
            <button
              className="btn small"
              disabled={!instruction.trim() || running}
              onClick={() => start(api.editCharacter(book.id, c.id, instruction)).then(() => setInstruction(""))}
            >
              {t("characters.apply_edit")}
            </button>
          </div>
          {c.versions.filter((v) => v.kind === "edit").length > 0 && (
            <ul className="small muted">
              {c.versions
                .filter((v) => v.kind === "edit")
                .map((v) => (
                  <li key={v.version}>
                    v{v.version}: {v.instruction}
                  </li>
                ))}
            </ul>
          )}
        </section>
      )}

      {/* 3. sheet */}
      {selected && (
        <section>
          <div className="row">
            <h4 style={{ margin: 0 }}>3. {t("characters.sheet")}</h4>
            <span className="spacer" />
            <button className="btn small" disabled={running} onClick={() => start(api.sheet(book.id, c.id))}>
              {sheet.length ? t("characters.redo_sheet") : t("characters.make_sheet")}
            </button>
          </div>
          {sheet.length > 0 && (
            <div className="grid-sm" style={{ marginBlockStart: 8 }}>
              {sheet.map((a) => (
                <div key={a.id} className="thumb square" onClick={() => setZoom(a.url)}>
                  <Img src={a.thumb_url} alt={c.name} />
                  <span className="idx">{t(`characters.views.${a.meta.view ?? a.meta.expression}`)}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 4. consistency */}
      {sheet.length > 0 && (
        <section>
          <div className="row">
            <h4 style={{ margin: 0 }}>4. {t("characters.consistency")}</h4>
            {cons && <Tag kind={cons.pass ? "ok" : "bad"}>{cons.pass ? t("characters.passed") : t("characters.failed")}</Tag>}
            {cons?.override && <Tag kind="warn">{t("characters.overridden")}</Tag>}
            <span className="spacer" />
            <button className="btn small" disabled={running} onClick={() => start(api.consistency(book.id, c.id))}>
              {cons ? t("characters.rerun_test") : t("characters.run_test")}
            </button>
          </div>
          {cons?.manual && tests.length > 0 && <p className="small muted">{t("characters.manual_verdict_help")}</p>}
          {cons?.manual && cons.results.some((r) => r.pass === null) && <Tag kind="warn">{t("characters.verdict_open")}</Tag>}
          {tests.length > 0 && (
            <div className="grid-sm" style={{ marginBlockStart: 8 }}>
              {tests.map((a) => {
                const r = cons?.results.find((x) => x.asset_id === a.id);
                return (
                  <div key={a.id}>
                    <div className={`thumb square ${r && !r.pass ? "rejected" : ""}`} onClick={() => setZoom(a.url)}>
                      <Img src={a.thumb_url} alt={c.name} />
                      {r && r.pass !== null && <span className={`badge tag ${r.pass ? "ok" : "bad"}`}>{r.pass ? "✓" : "✕"}</span>}
                      {r && r.pass === null && <span className="badge tag warn">?</span>}
                    </div>
                    {r && r.issues.length > 0 && <div className="small muted">{r.issues.join("; ")}</div>}
                    {r && cons?.manual && (
                      <div className="row" style={{ marginBlockStart: 4, gap: 4 }}>
                        <button className={`btn small ${r.pass === true ? "primary" : ""}`} aria-pressed={r.pass === true}
                                onClick={() => act.mutate(() => api.consistencyVerdict(book.id, c.id, a.id, true))}>
                          ✓ {t("characters.mark_pass")}
                        </button>
                        <button className={`btn small ${r.pass === false ? "danger" : ""}`} aria-pressed={r.pass === false}
                                onClick={() => act.mutate(() => api.consistencyVerdict(book.id, c.id, a.id, false))}>
                          ✕ {t("characters.mark_fail")}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div className="row" style={{ marginBlockStart: 10 }}>
            {c.status !== "approved" ? (
              <>
                <button className="btn primary small" disabled={!cons?.pass} onClick={() => act.mutate(() => api.approveCharacter(book.id, c.id))}>
                  {t("characters.approve")}
                </button>
                {cons && !cons.pass && (
                  <button className="btn small" onClick={() => window.confirm(t("characters.override_confirm")) && act.mutate(() => api.approveCharacter(book.id, c.id, true))}>
                    {t("characters.approve_override")}
                  </button>
                )}
              </>
            ) : (
              <>
                <button className="btn small" onClick={() => act.mutate(() => api.unapproveCharacter(book.id, c.id))}>
                  {t("characters.unapprove")}
                </button>
                {!c.in_library && (
                  <button className="btn small" onClick={() => act.mutate(() => api.toLibrary(book.id, c.id))}>
                    {t("characters.save_library")}
                  </button>
                )}
              </>
            )}
          </div>
        </section>
      )}
      {zoom && (
        <Modal onClose={() => setZoom(null)}>
          <Img src={zoom} alt={c.name} />
        </Modal>
      )}
    </div>
  );
}

function SampleSection({ book, ready, sampleOk, onChange }: { book: Book; ready: boolean; sampleOk: boolean; onChange: () => void }) {
  const { t } = useTranslation();
  const [jobId, setJobId] = useStepJob(book.id, ["sample_page"]);
  const { job, running } = useJob(jobId, onChange);
  const gen = useMutation({ mutationFn: () => api.sample(book.id), onSuccess: (j) => setJobId(j.id) });
  const approve = useMutation({ mutationFn: () => api.approveSample(book.id), onSuccess: onChange });
  const s = book.sample;
  return (
    <div className="card stack">
      <div className="row">
        <h3 style={{ margin: 0 }}>{t("characters.sample_title")}</h3>
        {sampleOk && <Tag kind="ok">{t("status.approved")}</Tag>}
      </div>
      {!ready && <div className="alert warn">{t("characters.sample_blocked")}</div>}
      {jobId && running && <JobProgress job={job} />}
      <ErrorBox error={gen.error || approve.error} />
      {s?.url && (
        <div className="thumb" style={{ maxWidth: 320 }}>
          <Img src={s.url} alt={t("characters.sample_title")} />
        </div>
      )}
      <div className="row">
        <button className="btn" disabled={!ready || running} onClick={() => gen.mutate()}>
          {s?.url ? t("characters.sample_again") : t("characters.sample_make")}
        </button>
        {s?.url && !sampleOk && (
          <button className="btn primary" onClick={() => approve.mutate()}>
            {t("characters.sample_approve")}
          </button>
        )}
      </div>
    </div>
  );
}

function LibraryPicker({ book, onClose, onPicked }: { book: Book; onClose: () => void; onPicked: () => void }) {
  const { t } = useTranslation();
  const lib = useQuery({ queryKey: ["library"], queryFn: api.library });
  const pick = useMutation({
    mutationFn: (id: number) => api.fromLibrary(book.id, id),
    onSuccess: () => {
      onPicked();
      onClose();
    },
  });
  return (
    <Modal onClose={onClose} title={t("characters.library")}>
      <ErrorBox error={lib.error || pick.error} />
      {lib.data?.length === 0 && <p className="muted">{t("characters.library_empty")}</p>}
      <div className="grid-sm">
        {lib.data?.map((c) => {
          const sel = c.assets.find((a) => a.kind === "candidate" && a.selected);
          return (
            <div key={c.id} className="card selectable" onClick={() => pick.mutate(c.id)}>
              {sel && (
                <div className="thumb square">
                  <Img src={sel.thumb_url} alt={c.name} />
                </div>
              )}
              <strong>{c.name}</strong>
              <div className="small muted">{c.species}</div>
            </div>
          );
        })}
      </div>
    </Modal>
  );
}
