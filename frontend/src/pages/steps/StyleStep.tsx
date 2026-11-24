import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { Recipe } from "../../api/types";
import { ErrorBox, Tag } from "../../components/ui";
import { addBlock, normalize, removeBlock, setShare } from "../../lib/mix";
import type { StepProps } from "../WizardPage";

const EMPTY: Recipe = { mood: "", age_group: "", line_weight: "bold", detail_level: "low", page_mix: [], confidence: "low", notes: "" };

// Preset choices (labels are translated under style.*). The values are what the prompts receive.
const MOODS = ["playful", "calm", "cozy", "adventurous", "educational", "magical", "funny", "bright"];
const AGES = ["2-4", "4-8", "8-12", "teens", "adults"];
const LINE_WEIGHTS = ["thin", "medium", "bold", "extra bold"];
const DETAIL_LEVELS = ["very low", "low", "medium", "high"];
const PAGE_TYPES = ["single_character", "scene", "pattern_mandala", "hidden_objects_scene", "maze", "dot_to_dot", "word_search", "trace_write", "qa_page", "story_text"];

const splitMoods = (s: string) => s.split(/[,،]/).map((x) => x.trim().toLowerCase()).filter(Boolean);
const key = (v: string) => v.replace(/[ -]/g, "_");

function Chips({ options, value, onPick, label }: { options: string[]; value: string[]; onPick: (v: string) => void; label: (v: string) => string }) {
  return (
    <div className="row" style={{ flexWrap: "wrap" }}>
      {options.map((o) => (
        <button key={o} type="button" aria-pressed={value.includes(o)} className={`btn small ${value.includes(o) ? "primary" : ""}`} onClick={() => onPick(o)}>
          {label(o)}
        </button>
      ))}
    </div>
  );
}

export default function StyleStep({ book }: StepProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [r, setR] = useState<Recipe>(book.recipe ?? EMPTY);
  const [saved, setSaved] = useState(false);
  useEffect(() => setR(book.recipe ?? EMPTY), [book.recipe]);
  const save = useMutation({
    mutationFn: () => api.saveRecipe(book.id, { ...r, page_mix: r.page_mix.length ? normalize(r.page_mix) : [] }),
    onSuccess: () => {
      setSaved(true);
      qc.invalidateQueries({ queryKey: ["book", book.id] });
    },
  });
  const patch = (p: Partial<Recipe>) => {
    setSaved(false);
    setR({ ...r, ...p });
  };

  const moods = splitMoods(r.mood);
  const toggleMood = (m: string) => patch({ mood: (moods.includes(m) ? moods.filter((x) => x !== m) : [...moods, m]).join(", ") });
  const extraMoods = moods.filter((m) => !MOODS.includes(m));
  const ageOptions = AGES.includes(r.age_group) || !r.age_group ? AGES : [...AGES, r.age_group];
  const used = r.page_mix.map((m) => m.type);
  const addable = PAGE_TYPES.filter((p) => !used.includes(p));
  const fetchStatus = book.fetch?.status;

  return (
    <div className="card stack">
      {!book.recipe && <div className="alert warn">{t("style.none")}</div>}
      {book.recipe && fetchStatus && fetchStatus !== "ok" && fetchStatus !== "none" && <div className="alert warn">{t("style.guess_warning")}</div>}
      <div className="row">
        <strong>{t("style.confidence")}</strong>
        <Tag kind={r.confidence}>{t(`confidence.${r.confidence}`)}</Tag>
        <span className="muted small">{t(`confidence.${r.confidence}_help`)}</span>
      </div>

      <div className="field">
        <label>{t("style.mood")}</label>
        <Chips options={[...MOODS, ...extraMoods]} value={moods} onPick={toggleMood} label={(m) => (MOODS.includes(m) ? t(`style.moods.${m}`) : m)} />
      </div>
      <div className="field">
        <label>{t("style.age_group")}</label>
        <Chips options={ageOptions} value={[r.age_group]} onPick={(v) => patch({ age_group: v })} label={(v) => (AGES.includes(v) ? t(`style.ages.${key(v)}`) : v)} />
      </div>
      <div className="field">
        <label>{t("style.line_weight")}</label>
        <Chips
          options={LINE_WEIGHTS.includes(r.line_weight) ? LINE_WEIGHTS : [...LINE_WEIGHTS, r.line_weight]}
          value={[r.line_weight]}
          onPick={(v) => patch({ line_weight: v })}
          label={(v) => (LINE_WEIGHTS.includes(v) ? t(`style.lw.${key(v)}`) : v)}
        />
      </div>
      <div className="field">
        <label>{t("style.detail_level")}</label>
        <Chips
          options={DETAIL_LEVELS.includes(r.detail_level) ? DETAIL_LEVELS : [...DETAIL_LEVELS, r.detail_level]}
          value={[r.detail_level]}
          onPick={(v) => patch({ detail_level: v })}
          label={(v) => (DETAIL_LEVELS.includes(v) ? t(`style.dl.${key(v)}`) : v)}
        />
      </div>

      <div className="field">
        <label>{t("style.page_mix")}</label>
        {r.page_mix.length === 0 && <span className="muted small">{t("style.no_mix")}</span>}
        {r.page_mix.map((m, i) => (
          <div className="row" key={m.type}>
            <span style={{ minInlineSize: 150 }}>{t(`page_types.${m.type}`)}</span>
            <input
              type="range"
              min={0}
              max={100}
              value={m.share}
              aria-label={t(`page_types.${m.type}`)}
              onChange={(e) => patch({ page_mix: setShare(r.page_mix, i, Number(e.target.value)) })}
              style={{ flex: 1 }}
            />
            <span style={{ minInlineSize: 40 }}>{m.share}%</span>
            <button type="button" className="btn small" disabled={r.page_mix.length <= 1} onClick={() => patch({ page_mix: removeBlock(r.page_mix, i) })} aria-label={t("common.delete")}>
              ✕
            </button>
          </div>
        ))}
        {addable.length > 0 && (
          <select
            value=""
            aria-label={t("style.add_page_type")}
            onChange={(e) => e.target.value && patch({ page_mix: r.page_mix.length ? addBlock(r.page_mix, e.target.value) : [{ type: e.target.value, share: 100 }] })}
          >
            <option value="">+ {t("style.add_page_type")}</option>
            {addable.map((p) => (
              <option key={p} value={p}>
                {t(`page_types.${p}`)}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="field">
        <label htmlFor="notes">{t("style.notes")}</label>
        <textarea id="notes" value={r.notes} onChange={(e) => patch({ notes: e.target.value })} />
      </div>
      <ErrorBox error={save.error} />
      <div className="row">
        <button className="btn primary" onClick={() => save.mutate()} disabled={save.isPending || !r.mood}>
          {t("common.save")}
        </button>
        {saved && <span className="muted small">{t("common.saved")}</span>}
      </div>
    </div>
  );
}
