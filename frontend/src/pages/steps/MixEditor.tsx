import { useTranslation } from "react-i18next";
import { addBlock, type Block, removeBlock, setShare, total } from "../../lib/mix";

export const CONTENT_TYPES = [
  "scene", "single_character", "pattern_mandala", "hidden_objects_scene",
  "maze", "dot_to_dot", "word_search", "trace_write", "qa_page", "story_text",
];

export default function MixEditor({ blocks, onChange }: { blocks: Block[]; onChange: (b: Block[]) => void }) {
  const { t } = useTranslation();
  const unused = CONTENT_TYPES.filter((c) => !blocks.some((b) => b.type === c));
  return (
    <div>
      {blocks.map((b, i) => (
        <div className="mix-row" key={b.type}>
          <span>{t(`page_types.${b.type}`)}</span>
          <input
            type="range"
            min={0}
            max={100}
            value={b.share}
            aria-label={t(`page_types.${b.type}`)}
            onChange={(e) => onChange(setShare(blocks, i, Number(e.target.value)))}
          />
          <input
            type="number"
            min={0}
            max={100}
            value={b.share}
            aria-label={`${t(`page_types.${b.type}`)} %`}
            onChange={(e) => onChange(setShare(blocks, i, Number(e.target.value)))}
          />
          <button className="btn small ghost" onClick={() => onChange(removeBlock(blocks, i))} disabled={blocks.length <= 1} aria-label={t("common.remove")}>
            ✕
          </button>
        </div>
      ))}
      <div className="row">
        <span className={`tag ${total(blocks) === 100 ? "ok" : "bad"}`}>{t("format.total", { total: total(blocks) })}</span>
        {unused.length > 0 && (
          <select value="" onChange={(e) => e.target.value && onChange(addBlock(blocks, e.target.value))} style={{ maxWidth: 240 }} aria-label={t("format.add_type")}>
            <option value="">+ {t("format.add_type")}</option>
            {unused.map((u) => (
              <option key={u} value={u}>
                {t(`page_types.${u}`)}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}
