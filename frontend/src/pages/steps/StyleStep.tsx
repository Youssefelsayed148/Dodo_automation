import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { Recipe } from "../../api/types";
import { ErrorBox, Tag } from "../../components/ui";
import { normalize } from "../../lib/mix";
import type { StepProps } from "../WizardPage";

const EMPTY: Recipe = { mood: "", age_group: "", line_weight: "bold", detail_level: "low", page_mix: [], confidence: "low", notes: "" };

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
  const set = (k: keyof Recipe, v: string) => {
    setSaved(false);
    setR({ ...r, [k]: v });
  };

  return (
    <div className="card stack">
      {!book.recipe && <div className="alert warn">{t("style.none")}</div>}
      <div className="row">
        <strong>{t("style.confidence")}</strong>
        <Tag kind={r.confidence}>{t(`confidence.${r.confidence}`)}</Tag>
        <span className="muted small">{t(`confidence.${r.confidence}_help`)}</span>
      </div>
      <div className="grid">
        <div className="field">
          <label htmlFor="mood">{t("style.mood")}</label>
          <input id="mood" type="text" value={r.mood} onChange={(e) => set("mood", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="age">{t("style.age_group")}</label>
          <input id="age" type="text" value={r.age_group} onChange={(e) => set("age_group", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="lw">{t("style.line_weight")}</label>
          <select id="lw" value={r.line_weight} onChange={(e) => set("line_weight", e.target.value)}>
            {["thin", "medium", "bold", "extra bold"].map((v) => (
              <option key={v} value={v}>
                {t(`style.lw.${v.replace(" ", "_")}`)}
              </option>
            ))}
            {!["thin", "medium", "bold", "extra bold"].includes(r.line_weight) && <option value={r.line_weight}>{r.line_weight}</option>}
          </select>
        </div>
        <div className="field">
          <label htmlFor="dl">{t("style.detail_level")}</label>
          <select id="dl" value={r.detail_level} onChange={(e) => set("detail_level", e.target.value)}>
            {["very low", "low", "medium", "high"].map((v) => (
              <option key={v} value={v}>
                {t(`style.dl.${v.replace(" ", "_")}`)}
              </option>
            ))}
            {!["very low", "low", "medium", "high"].includes(r.detail_level) && <option value={r.detail_level}>{r.detail_level}</option>}
          </select>
        </div>
      </div>
      <div className="field">
        <label>{t("style.page_mix")}</label>
        <div className="row">
          {r.page_mix.length === 0 && <span className="muted small">{t("style.no_mix")}</span>}
          {r.page_mix.map((m) => (
            <Tag key={m.type}>
              {t(`page_types.${m.type}`)} {m.share}%
            </Tag>
          ))}
        </div>
      </div>
      <div className="field">
        <label htmlFor="notes">{t("style.notes")}</label>
        <textarea id="notes" value={r.notes} onChange={(e) => set("notes", e.target.value)} />
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
