import { useEffect, useState } from 'react';

/**
 * Mirrors document theme: `data-theme` on `html`/`body` overrides
 * `prefers-color-scheme` (same rules as `AvatarChatOverlay` before extraction).
 */
export function useDocumentDarkMode(): boolean {
    const [isDark, setIsDark] = useState(false);

    useEffect(() => {
        if (typeof window === 'undefined') return;

        const media = window.matchMedia('(prefers-color-scheme: dark)');
        const root = document.documentElement;
        const body = document.body;
        const compute = () => {
            const forced = root.getAttribute('data-theme') ?? body.getAttribute('data-theme');
            if (forced === 'dark') return true;
            if (forced === 'light') return false;
            return media.matches;
        };
        const sync = () => setIsDark(compute());

        sync();
        media.addEventListener('change', sync);
        const obs = new MutationObserver(sync);
        obs.observe(root, { attributes: true, attributeFilter: ['data-theme'] });
        obs.observe(body, { attributes: true, attributeFilter: ['data-theme'] });
        return () => {
            media.removeEventListener('change', sync);
            obs.disconnect();
        };
    }, []);

    return isDark;
}
