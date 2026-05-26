import { useCallback, useLayoutEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { activateSkipToMain } from '../utils/focusMainContent';
import { useSkipLinkTabOrder } from '../hooks/useSkipLinkTabOrder';

const SKIP_MOUNT_ID = 'skip-to-main';
const SKIP_LINK_ID = 'skip-to-content-link';

/**
 * WCAG 2.4.1 — first focusable stop on the page.
 * The anchor lives in index.html so Tab works before React hydrates.
 */
const SkipToMainLink: React.FC = () => {
    const { t } = useTranslation();
    useSkipLinkTabOrder(true);

    const onActivate = useCallback((e: Event) => {
        e.preventDefault();
        activateSkipToMain();
    }, []);

    useLayoutEffect(() => {
        const mount = document.getElementById(SKIP_MOUNT_ID);
        if (!mount) return;

        const syncInert = () => {
            const onboardingOpen = !!document.querySelector('.onboarding-overlay');
            if (onboardingOpen) mount.setAttribute('inert', '');
            else mount.removeAttribute('inert');
        };
        syncInert();
        const observer = new MutationObserver(syncInert);
        observer.observe(document.body, { childList: true, subtree: true });

        if (document.body.firstElementChild !== mount) {
            document.body.prepend(mount);
        }

        let link = document.getElementById(SKIP_LINK_ID) as HTMLAnchorElement | null;
        if (!link) {
            link = document.createElement('a');
            link.id = SKIP_LINK_ID;
            link.className = 'skip-to-content';
            link.href = '#main-content';
            mount.appendChild(link);
        }

        link.textContent = t('app.skipToContent');
        // tabindex 1 = first Tab stop even when focus was left on in-app chrome (WCAG skip link pattern).
        link.tabIndex = 1;
        link.addEventListener('click', onActivate);
        return () => {
            observer.disconnect();
            mount.removeAttribute('inert');
            link?.removeEventListener('click', onActivate);
        };
    }, [t, onActivate]);

    return null;
};

export default SkipToMainLink;
