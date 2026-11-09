import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { SettingsValues } from "../api/types";
import { ErrorBox, Tag } from "../components/ui";
import { TRIM_SIZES } from "../lib/specs";

export default function SettingsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [v, setV] = useState<SettingsValues | null>(null);
  useEffect(() => {
    if (s.data) setV(s.data.values);
  }, [s.data]);
  const save = useMutation({
    mutationFn: () => api.saveSettings(v!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
  const connect = useMutation({
    mutationFn: api.driveConnect,
    onSuccess: (r) => {
      window.open(r.auth_url, "_blank", "noopener");
    },
  });
  const disconnect = useMutation({ mutationFn: api.driveDisconnect, onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }) });

  if (s.error) return <ErrorBox error={s.error} />;
  if (!s.data || !v) return <div className="muted">{t("common.loading")}</div>;
  const set = <K extends keyof SettingsValues>(k: K, val: SettingsValues[K]) => setV({ ...v, [k]: val });
  const prov = s.data.providers;

  return (
    <div className="stack">
      <h1>{t("settings.title")}</h1>
      <div className="card">
        <div className="row">
          <h3 style={{ margin: 0 }}>{t("settings.manual_title")}</h3>
          <Tag kind={s.data.manual?.active ? "ok" : ""}>{s.data.manual?.active ? t("settings.manual_active") : t("settings.manual_inactive")}</Tag>
        </div>
        <p className="muted small">{t("settings.manual_help")}</p>
        <div className="field">
          <label htmlFor="mm">{t("settings.manual_title")}</label>
          <select
            id="mm"
            value={v.manual_mode === null || v.manual_mode === undefined ? "auto" : v.manual_mode ? "on" : "off"}
            onChange={(e) => set("manual_mode", e.target.value === "auto" ? null : e.target.value === "on")}
          >
            <option value="auto">{t("settings.manual_auto")}</option>
            <option value="on">{t("settings.manual_on")}</option>
            <option value="off">{t("settings.manual_off")}</option>
          </select>
        </div>
      </div>

      <div className="card">
        <h3>{t("settings.generation")}</h3>
        <div className="grid">
          <div className="field">
            <label htmlFor="bs">{t("settings.batch_size")}</label>
            <select id="bs" value={v.batch_size} onChange={(e) => set("batch_size", Number(e.target.value) as 5 | 10)}>
              <option value={5}>5</option>
              <option value={10}>10</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="cc">{t("settings.concurrency")}</label>
            <input id="cc" type="number" min={1} max={16} value={v.concurrency} onChange={(e) => set("concurrency", Number(e.target.value))} />
          </div>
          <div className="field">
            <label htmlFor="mr">{t("settings.max_redo")}</label>
            <input id="mr" type="number" min={0} max={5} value={v.max_redo} onChange={(e) => set("max_redo", Number(e.target.value))} />
          </div>
          <div className="field">
            <label htmlFor="ceil">{t("settings.cost_ceiling")}</label>
            <input id="ceil" type="number" min={0} step={0.5} value={v.cost_ceiling_usd} onChange={(e) => set("cost_ceiling_usd", Number(e.target.value))} />
            <div className="muted small">{t("settings.cost_ceiling_help")}</div>
          </div>
          <div className="field">
            <label htmlFor="trim">{t("settings.default_trim")}</label>
            <select id="trim" value={v.default_trim_size} onChange={(e) => set("default_trim_size", e.target.value)}>
              {Object.keys(TRIM_SIZES).map((k) => (
                <option key={k} value={k}>
                  {t(`specs.trims.${k}`, { defaultValue: k })}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="dl">{t("settings.default_language")}</label>
            <select id="dl" value={v.default_language} onChange={(e) => set("default_language", e.target.value as "en" | "ar")}>
              <option value="en">{t("lang.en")}</option>
              <option value="ar">{t("lang.ar")}</option>
            </select>
          </div>
        </div>
        <label className="checkbox">
          <input type="checkbox" checked={v.vision_qa} onChange={(e) => set("vision_qa", e.target.checked)} />
          {t("settings.vision_qa")}
        </label>
      </div>

      <div className="card">
        <h3>{t("settings.providers")}</h3>
        <div className="field">
          <label htmlFor="ip">{t("settings.image_provider")}</label>
          <select id="ip" value={v.image_provider} onChange={(e) => set("image_provider", e.target.value)}>
            <option value="">{t("settings.provider_env", { name: prov.env_image_provider })}</option>
            {prov.image.map((p) => (
              <option key={p.name} value={p.name} disabled={!p.configured}>
                {p.name} ({p.model}){p.configured ? "" : ` – ${t("settings.not_configured")}`}
              </option>
            ))}
          </select>
          <div className="muted small">{t("settings.provider_help")}</div>
        </div>
        <div className="row small">
          <span>{t("settings.text_llm")}:</span>
          <Tag kind={prov.text === "mock" ? "warn" : "ok"}>{prov.text === "mock" ? t("settings.mock") : prov.text_model}</Tag>
        </div>
        <div className="row" style={{ marginBlockStart: 10 }}>
          <Link className="btn small" to="/settings/compare">
            {t("settings.compare_link")}
          </Link>
        </div>
      </div>
      <ErrorBox error={save.error} />
      <div className="row">
        <button className="btn primary" onClick={() => save.mutate()} disabled={save.isPending}>
          {t("common.save")}
        </button>
        {save.isSuccess && <span className="muted small">{t("common.saved")}</span>}
      </div>

      <div className="card">
        <h3>{t("settings.drive")}</h3>
        {!s.data.drive.configured ? (
          <div className="alert">{t("settings.drive_not_configured")}</div>
        ) : (
          <div className="row">
            <Tag kind={s.data.drive.connected ? "ok" : ""}>{s.data.drive.connected ? t("settings.drive_connected") : t("settings.drive_disconnected")}</Tag>
            {s.data.drive.connected ? (
              <button className="btn small danger" onClick={() => disconnect.mutate()}>
                {t("settings.drive_disconnect")}
              </button>
            ) : (
              <button className="btn small primary" onClick={() => connect.mutate()}>
                {t("settings.drive_connect")}
              </button>
            )}
            <button className="btn small" onClick={() => qc.invalidateQueries({ queryKey: ["settings"] })}>
              {t("common.refresh")}
            </button>
          </div>
        )}
        <ErrorBox error={connect.error || disconnect.error} />
      </div>
    </div>
  );
}
