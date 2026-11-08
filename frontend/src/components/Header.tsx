import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";
import { api } from "../api/client";

const THEME_KEY = "dodo.theme";

export function Header() {
  const { t, i18n } = useTranslation();
  const [theme, setTheme] = useState<string>(() => {
    try {
      return localStorage.getItem(THEME_KEY) || "system";
    } catch {
      return "system";
    }
  });

  useEffect(() => {
    if (theme === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  const toggleLang = () => {
    const next = i18n.language === "ar" ? "en" : "ar";
    i18n.changeLanguage(next);
    api.saveSettings({ ui_language: next }).catch(() => undefined);
  };
  const nextTheme = theme === "system" ? "light" : theme === "light" ? "dark" : "system";

  return (
    <header className="header">
      <NavLink to="/" className="brand">
        <span className="brand-mark" aria-hidden>
          D
        </span>
        <span>{t("app.name")}</span>
      </NavLink>
      <nav className="nav">
        <NavLink to="/" end>
          {t("nav.books")}
        </NavLink>
        <NavLink to="/settings">{t("nav.settings")}</NavLink>
        <button className="btn small" onClick={() => setTheme(nextTheme)} aria-label={t("nav.theme")}>
          {t(`color_theme.${theme}`)}
        </button>
        <button className="btn small primary" onClick={toggleLang} aria-label={t("nav.language")}>
          {i18n.language === "ar" ? "English" : "العربية"}
        </button>
      </nav>
    </header>
  );
}
