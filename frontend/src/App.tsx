import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import { Header } from "./components/Header";
import { LANG_KEY } from "./i18n";
import BooksPage from "./pages/BooksPage";
import ComparePage from "./pages/ComparePage";
import SettingsPage from "./pages/SettingsPage";
import WizardPage from "./pages/WizardPage";

export default function App() {
  const { t, i18n } = useTranslation();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });

  // First run on this browser: take the UI language saved on the backend.
  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(LANG_KEY);
    } catch {
      stored = null;
    }
    const remote = settings.data?.values.ui_language;
    if (!stored && remote && remote !== i18n.language) i18n.changeLanguage(remote);
  }, [settings.data, i18n]);

  return (
    <div className="app">
      <Header />
      <main className="main">
        {settings.isError && <div className="alert error">{t("errors.backend_down")}</div>}
        <Routes>
          <Route path="/" element={<BooksPage />} />
          <Route path="/books/:id/:step?" element={<WizardPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/compare" element={<ComparePage />} />
          <Route path="*" element={<BooksPage />} />
        </Routes>
      </main>
    </div>
  );
}
