import React, { useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { CU_SETTINGS_TEXT_SIZE_KEY, THEME_STORAGE_KEY } from '../cu/constants';
import CUControls from '../cu/CUControls';
import OnboardingOverlay from '../cu/overlays/onboarding/OnboardingOverlay';
import CoinPoiOverlay from '../cu/overlays/CoinPoiOverlay';
import { useControl, useStream, useChat, useAppUI, useSpatialSound } from './contexts';

const CuViewLayer: React.FC = () => {
    const ctrl = useControl();
    const stream = useStream();
    const chat = useChat();
    const appUI = useAppUI();
    const spatialSound = useSpatialSound();

    useLayoutEffect(() => {
        if (typeof document === 'undefined') return;
        try {
            const raw = window.localStorage.getItem(CU_SETTINGS_TEXT_SIZE_KEY);
            const n = raw != null ? Number(raw) : 100;
            const pct = Number.isFinite(n) ? Math.min(115, Math.max(85, n)) : 100;
            document.documentElement.style.setProperty('--cu-app-font-scale', String(pct / 100));
        } catch {
            document.documentElement.style.setProperty('--cu-app-font-scale', '1');
        }
        try {
            const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
            if (saved === 'light' || saved === 'dark') {
                document.documentElement.setAttribute('data-theme', saved);
            }
        } catch {
            /* ignore */
        }
    }, []);

    return (
        <>
            {!appUI.seatArrivalCelebrationVisible && !appUI.poiArrivalVisible && !appUI.onboardingVisible && !ctrl.videobookOpen && !spatialSound.isOpen && (!ctrl.avatarChatOpen || chat.chatOpenSource === 'search') && (
                appUI.streamNavOverlayActive && appUI.seatRouteCuPortalEl
                    ? createPortal(<CUControls />, appUI.seatRouteCuPortalEl)
                    : /* Fallback: keep CU chrome when overlay is active but portal node is missing (e.g. timing) */
                      <CUControls />
            )}

            {appUI.onboardingVisible && stream.streamReady && !stream.sceneLoading && (
                <OnboardingOverlay />
            )}

            <CoinPoiOverlay />
        </>
    );
};

export default CuViewLayer;
