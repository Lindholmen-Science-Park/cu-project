import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import en from './locales/en.json';
import sv from './locales/sv.json';
import fr from './locales/fr.json';
import es from './locales/es.json';

i18n
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
        resources: {
            en: { translation: en },
            sv: { translation: sv },
            fr: { translation: fr },
            es: { translation: es },
        },
        fallbackLng: 'en',
        supportedLngs: ['en', 'sv', 'fr', 'es'],
        interpolation: {
            escapeValue: false,
        },
        detection: {
            order: [],
            caches: [],
            // To persist language choice across sessions, change to:
            // order: ['localStorage'],
            // caches: ['localStorage'],
        },
    });

/**
 * Keep the document's <html lang> attribute and <title> in sync with the
 * active i18n language so screen readers announce content in the correct
 * voice and pronunciation (WCAG 3.1.1 / 3.1.2).
 */
function syncDocumentLanguage(lang: string): void {
    if (typeof document === 'undefined') return;
    const base = String(lang || 'en').split('-')[0].toLowerCase();
    if (document.documentElement.lang !== base) {
        document.documentElement.lang = base;
    }
    const title = i18n.t('app.documentTitle');
    if (title && typeof title === 'string' && document.title !== title) {
        document.title = title;
    }
}

if (typeof window !== 'undefined') {
    if (i18n.isInitialized) {
        syncDocumentLanguage(i18n.language);
    } else {
        i18n.on('initialized', () => syncDocumentLanguage(i18n.language));
    }
    i18n.on('languageChanged', (lng) => syncDocumentLanguage(lng));
}

export default i18n;
