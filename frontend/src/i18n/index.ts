import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./ar.json";
import en from "./en.json";

export const LANG_KEY = "dodo.lang";

function initialLang(): "en" | "ar" {
  try {
    const v = localStorage.getItem(LANG_KEY);
    if (v === "en" || v === "ar") return v;
  } catch {
    /* storage may be unavailable */
  }
  return "en";
}

export function applyDocumentLang(lang: string) {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: initialLang(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

applyDocumentLang(i18n.language);
i18n.on("languageChanged", (lng) => {
  applyDocumentLang(lng);
  try {
    localStorage.setItem(LANG_KEY, lng);
  } catch {
    /* ignore */
  }
});

export default i18n;
