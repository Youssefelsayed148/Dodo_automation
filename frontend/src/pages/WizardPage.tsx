import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Book, Gates } from "../api/types";
import { ErrorBox } from "../components/ui";
import CharactersStep from "./steps/CharactersStep";
import ExportPromptsPanel from "./steps/ExportPromptsPanel";
import ExportStep from "./steps/ExportStep";
import FormatStep from "./steps/FormatStep";
import GenerateStep from "./steps/GenerateStep";
import ReviewStep from "./steps/ReviewStep";
import SourceStep from "./steps/SourceStep";
import SpecsStep from "./steps/SpecsStep";
import StyleStep from "./steps/StyleStep";
import ThemeStep from "./steps/ThemeStep";

export const STEPS = ["source", "style", "theme", "format", "characters", "specs", "generate", "review", "export"] as const;
export type StepId = (typeof STEPS)[number];

const pageTotal = (b: Book) => Object.values(b.page_status_counts).reduce((s, n) => s + n, 0);

export function canLeave(step: StepId, b: Book, gates?: Gates): boolean {
  switch (step) {
    case "source":
    case "style":
      return !!b.recipe;
    case "theme":
      return !!b.theme_id;
    case "format":
      return !!b.format_id;
    case "characters":
      return !!gates && gates.characters_ok && gates.sample_ok;
    case "specs":
      return pageTotal(b) > 0;
    case "generate": {
      const c = b.page_status_counts;
      return pageTotal(b) > 0 && !c.queued && !c.planned;
    }
    case "review":
      return (b.page_status_counts.approved ?? 0) > 0;
    default:
      return true;
  }
}

/** Furthest step the book may open (all earlier steps satisfied). */
export function maxStep(b: Book, gates?: Gates): number {
  let i = 0;
  while (i < STEPS.length - 1 && canLeave(STEPS[i], b, gates)) i++;
  return i;
}

function defaultStep(b: Book, gates?: Gates): StepId {
  return STEPS[maxStep(b, gates)];
}

export default function WizardPage() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const params = useParams();
  const id = Number(params.id);
  const [promptsOpen, setPromptsOpen] = useState(false);
  const book = useQuery({ queryKey: ["book", id], queryFn: () => api.book(id), enabled: Number.isFinite(id) });
  const chars = useQuery({ queryKey: ["characters", id], queryFn: () => api.characters(id), enabled: Number.isFinite(id) });

  if (book.error) return <ErrorBox error={book.error} />;
  if (!book.data) return <div className="muted">{t("common.loading")}</div>;
  const b = book.data;
  const gates = chars.data?.gates;
  const current: StepId = (STEPS as readonly string[]).includes(params.step ?? "") ? (params.step as StepId) : defaultStep(b, gates);
  const idx = STEPS.indexOf(current);
  const reachable = maxStep(b, gates);
  const go = (s: StepId) => nav(`/books/${id}/${s}`);
  const next = () => idx < STEPS.length - 1 && go(STEPS[idx + 1]);
  const back = () => (idx > 0 ? go(STEPS[idx - 1]) : nav("/"));
  const ok = canLeave(current, b, gates);

  const props = { book: b, onNext: next };
  return (
    <div>
      <div className="row" style={{ marginBlockEnd: 4 }}>
        <h1 style={{ margin: 0 }}>{b.title}</h1>
        <span className="spacer" />
        {idx >= 3 && (
          <button className="btn small" onClick={() => setPromptsOpen(true)}>
            {t("prompts.open")}
          </button>
        )}
      </div>
      <nav className="stepbar" aria-label={t("wizard.steps")}>
        {STEPS.map((s, i) => (
          <button
            key={s}
            className={`step-chip ${i === idx ? "current" : ""} ${i < idx ? "done" : ""}`}
            disabled={i > reachable && i !== idx}
            onClick={() => go(s)}
            aria-current={i === idx ? "step" : undefined}
          >
            <span className="num">{i + 1}</span>
            {t(`steps.${s}.short`)}
          </button>
        ))}
      </nav>
      <h2>{t(`steps.${current}.title`)}</h2>
      <p className="muted">{t(`steps.${current}.help`)}</p>
      {current === "source" && <SourceStep {...props} />}
      {current === "style" && <StyleStep {...props} />}
      {current === "theme" && <ThemeStep {...props} />}
      {current === "format" && <FormatStep {...props} />}
      {current === "characters" && <CharactersStep {...props} />}
      {current === "specs" && <SpecsStep {...props} />}
      {current === "generate" && <GenerateStep {...props} />}
      {current === "review" && <ReviewStep {...props} />}
      {current === "export" && <ExportStep {...props} />}
      <div className="navbar">
        <button className="btn" onClick={back}>
          {t("common.back")}
        </button>
        {!ok && idx < STEPS.length - 1 && <span className="muted small">{t(`steps.${current}.blocked`)}</span>}
        {idx < STEPS.length - 1 ? (
          <button className="btn primary" onClick={next} disabled={!ok}>
            {t("common.next")}
          </button>
        ) : (
          <button className="btn primary" onClick={() => nav("/")}>
            {t("common.finish")}
          </button>
        )}
      </div>
      {promptsOpen && <ExportPromptsPanel book={b} onClose={() => setPromptsOpen(false)} />}
    </div>
  );
}

export interface StepProps {
  book: Book;
  onNext: () => void;
}
