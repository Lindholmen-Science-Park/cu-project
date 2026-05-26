import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppMode } from '../../context/AppModeContext';
import SettingsPanel from './controls/SettingsPanel';
import PeoplePanel from './controls/PeoplePanel';
import ControlsMenu from './controls/ControlsMenu';
import { SettingsMenuListIcon } from './controls/settings-icons/SettingsIcons';
import './CUControls.css';
import '../streaming/DarkMode.css';
import { useCuModalBackgroundInert } from './hooks/useCuModalBackgroundInert';

import { useStream, useNavigation, useControl, useAppUI, useEnvironment } from '../streaming/contexts';
import { beginViewTransition } from '../streaming/viewTransition';
import { sendMessage } from '../streaming/messaging';
import toggleOverviewSvg from '@icons/map-markers/toggleOverview.svg';

const ViewToggleExploreIcon: React.FC = () => (
    <svg
        className="cu-view-toggle-icon cu-view-toggle-icon--explore"
        xmlns="http://www.w3.org/2000/svg"
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden
    >
        <path
            d="M12.0006 2.73758C12.0006 2.17065 12.228 1.62694 12.6329 1.22607C13.0378 0.825187 13.5869 0.599976 14.1595 0.599976C14.7321 0.599976 15.2812 0.825187 15.6861 1.22607C16.091 1.62694 16.3184 2.17065 16.3184 2.73758C16.3184 3.30451 16.091 3.84822 15.6861 4.24909C15.2812 4.64997 14.7321 4.87518 14.1595 4.87518C13.5869 4.87518 13.0378 4.64997 12.6329 4.24909C12.228 3.84822 12.0006 3.30451 12.0006 2.73758ZM10.4938 9.47549C10.4488 9.4933 10.4084 9.51111 10.3634 9.52893L10.0036 9.68479C9.26593 10.0099 8.69921 10.6289 8.44284 11.386L8.3259 11.7333C8.07402 12.4815 7.25993 12.8823 6.50431 12.6329C5.74868 12.3835 5.34389 11.5775 5.59576 10.8293L5.7127 10.4819C6.22545 8.96335 7.35888 7.72532 8.83414 7.07514L9.19396 6.91927C10.1295 6.50956 11.1415 6.2958 12.167 6.2958C14.173 6.2958 15.9811 7.4893 16.7502 9.31962L17.4429 10.9629L18.4054 11.4394C19.116 11.7912 19.4039 12.6463 19.0485 13.3499C18.6932 14.0535 17.8297 14.3385 17.119 13.9867L15.9136 13.3944C15.4503 13.1629 15.086 12.7799 14.8881 12.3034L14.4563 11.2791L13.5883 14.196L15.8147 16.6008C16.0575 16.8636 16.2285 17.1798 16.3184 17.5271L17.3529 21.6287C17.5463 22.3902 17.0785 23.1651 16.3049 23.3566C15.5313 23.548 14.7532 23.0849 14.5598 22.3189L13.5703 18.3955L10.3904 14.962C9.7247 14.245 9.47732 13.243 9.7292 12.3034L10.4893 9.47549H10.4938ZM7.89411 18.3243L9.01855 15.5454C9.113 15.679 9.22095 15.8037 9.33339 15.9284L11.164 17.9057L10.5118 19.5178C10.4039 19.785 10.2419 20.0299 10.035 20.2348L7.25993 22.9825C6.69771 23.5391 5.78467 23.5391 5.22245 22.9825C4.66023 22.4258 4.66023 21.5218 5.22245 20.9651L7.89411 18.3243Z"
            fill="currentColor"
        />
    </svg>
);

const PeopleIcon: React.FC = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="23" height="23" viewBox="0 0 23 23" fill="none" className="cu-icon-btn-svg" aria-hidden>
        <path
            d="M2.875 7.18769C2.875 6.99706 2.95073 6.81424 3.08552 6.67944C3.22032 6.54465 3.40314 6.46892 3.59377 6.46892H6.93334C7.08826 5.94995 7.40654 5.49483 7.84085 5.17124C8.27515 4.84764 8.8023 4.67285 9.3439 4.67285C9.8855 4.67285 10.4126 4.84764 10.847 5.17124C11.2813 5.49483 11.5995 5.94995 11.7545 6.46892H19.4066C19.5973 6.46892 19.7801 6.54465 19.9149 6.67944C20.0497 6.81424 20.1254 6.99706 20.1254 7.18769C20.1254 7.37832 20.0497 7.56114 19.9149 7.69593C19.7801 7.83073 19.5973 7.90645 19.4066 7.90645H11.7545C11.5995 8.42543 11.2813 8.88054 10.847 9.20414C10.4126 9.52773 9.8855 9.70252 9.3439 9.70252C8.8023 9.70252 8.27515 9.52773 7.84085 9.20414C7.40654 8.88054 7.08826 8.42543 6.93334 7.90645H3.59377C3.40314 7.90645 3.22032 7.83073 3.08552 7.69593C2.95073 7.56114 2.875 7.37832 2.875 7.18769ZM19.4066 15.0941H17.5046C17.3497 14.5751 17.0314 14.12 16.5971 13.7964C16.1628 13.4728 15.6356 13.2981 15.094 13.2981C14.5524 13.2981 14.0253 13.4728 13.591 13.7964C13.1567 14.12 12.8384 14.5751 12.6835 15.0941H3.59377C3.40314 15.0941 3.22032 15.1698 3.08552 15.3046C2.95073 15.4394 2.875 15.6223 2.875 15.8129C2.875 16.0035 2.95073 16.1863 3.08552 16.3211C3.22032 16.4559 3.40314 16.5317 3.59377 16.5317H12.6835C12.8384 17.0506 13.1567 17.5057 13.591 17.8293C14.0253 18.1529 14.5524 18.3277 15.094 18.3277C15.6356 18.3277 16.1628 18.1529 16.5971 17.8293C17.0314 17.5057 17.3497 17.0506 17.5046 16.5317H19.4066C19.5973 16.5317 19.7801 16.4559 19.9149 16.3211C20.0497 16.1863 20.1254 16.0035 20.1254 15.8129C20.1254 15.6223 20.0497 15.4394 19.9149 15.3046C19.7801 15.1698 19.5973 15.0941 19.4066 15.0941Z"
            fill="currentColor"
        />
    </svg>
);

const CUControls: React.FC = () => {
    const { t } = useTranslation();
    const { setMode } = useAppMode();
    const stream = useStream();
    const nav = useNavigation();
    const ctrl = useControl();
    const appUI = useAppUI();
    const env = useEnvironment();

    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [isPeopleOpen, setIsPeopleOpen] = useState(false);
    const [isSettingsPanelOpen, setIsSettingsPanelOpen] = useState(false);

    const hideCuChrome =
        appUI.streamNavOverlayActive || nav.restroomWidgetOpen || nav.quietZoneWidgetOpen;

    const cuModalOpen = isPeopleOpen || isMenuOpen || isSettingsPanelOpen;
    useCuModalBackgroundInert(cuModalOpen);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        const onToggle = () => {
            setIsMenuOpen((prev) => !prev);
            setIsPeopleOpen(false);
            setIsSettingsPanelOpen(false);
        };
        const onReopen = () => {
            setIsMenuOpen(false);
            setIsPeopleOpen(false);
            setIsSettingsPanelOpen(false);
            requestAnimationFrame(() => setIsMenuOpen(true));
        };
        window.addEventListener('cu-controls-toggle-menu', onToggle);
        window.addEventListener('cu-controls-reopen-menu', onReopen);
        const onOpenWorldSettings = () => {
            setIsSettingsPanelOpen(false);
            setIsMenuOpen(false);
            setIsPeopleOpen(true);
        };
        window.addEventListener('cu-open-3d-world-settings', onOpenWorldSettings);
        return () => {
            window.removeEventListener('cu-controls-toggle-menu', onToggle);
            window.removeEventListener('cu-controls-reopen-menu', onReopen);
            window.removeEventListener('cu-open-3d-world-settings', onOpenWorldSettings);
        };
    }, []);

    useEffect(() => {
        if (hideCuChrome) {
            setIsMenuOpen(false);
            setIsSettingsPanelOpen(false);
            setIsPeopleOpen(false);
        }
    }, [hideCuChrome]);

    if (!stream.streamReady || appUI.isViewer) return null;

    const toggleMenu = () => {
        setIsMenuOpen((prev) => !prev);
        if (isPeopleOpen) setIsPeopleOpen(false);
        setIsSettingsPanelOpen(false);
    };

    const togglePeople = () => {
        setIsPeopleOpen((prev) => !prev);
        if (isMenuOpen) setIsMenuOpen(false);
        setIsSettingsPanelOpen(false);
    };

    const closeMenu = () => setIsMenuOpen(false);

    const openSettingsPanel = () => {
        setIsPeopleOpen(false);
        setIsSettingsPanelOpen(true);
        setIsMenuOpen(false);
    };

    const closeSettingsPanel = () => setIsSettingsPanelOpen(false);

    const closeSettingsAndOpenControlsMenu = () => {
        setIsSettingsPanelOpen(false);
        setIsPeopleOpen(false);
        setIsMenuOpen(true);
    };

    const switchToDevMode = () => {
        setIsMenuOpen(false);
        setIsPeopleOpen(false);
        setIsSettingsPanelOpen(false);
        setMode('dev');
    };

    const handleViewToggle = useCallback(() => {
        const isBirdEye = env.currentCamera === 'bird_eye';
        const target = isBirdEye ? 'first_person' : 'bird_eye';

        if (isBirdEye) {
            nav.clearPoiRouteState();
            ctrl.setBirdEyeRoutePoints(null);
            try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch {}
            try { sendMessage('birdEyeRouteClear', {}); } catch {}
        }

        beginViewTransition({
            target: target === 'first_person' ? 'firstPerson' : 'birdEye',
            message: target === 'first_person'
                ? t('streaming.switchingFirstPerson')
                : t('streaming.switchingOverview'),
            onFadeOutComplete: () => {
                env.handleCameraChange(target);
            },
        });
    }, [env, nav, ctrl, t]);

    return (
        <div className={`cu-controls${appUI.streamNavOverlayActive ? ' cu-controls--seat-route-embed' : ''}`}>
            {/* Hamburger, people, and view toggle hidden while Quick settings is open */}
            {!hideCuChrome && !isPeopleOpen && (
                <button
                    className={`cu-hamburger ${isMenuOpen ? 'open' : ''}`}
                    onClick={toggleMenu}
                    title={t('controls.openControls')}
                    aria-label={t('controls.openControls')}
                    type="button"
                    aria-expanded={isMenuOpen}
                    aria-controls="cu-controls-menu-dialog"
                >
                    <SettingsMenuListIcon />
                </button>
            )}

            {!hideCuChrome && !isPeopleOpen && (
                <button
                    type="button"
                    className={`cu-icon-btn ${isPeopleOpen ? 'active' : ''}`}
                    onClick={togglePeople}
                    title={t('controls.peopleGroups')}
                    aria-label={t('controls.peopleGroups')}
                    aria-expanded={isPeopleOpen}
                    aria-pressed={isPeopleOpen}
                >
                    <PeopleIcon />
                </button>
            )}

            {!hideCuChrome && !isPeopleOpen && (
                <button
                    type="button"
                    className={
                        env.currentCamera === 'bird_eye'
                            ? 'cu-view-toggle-btn cu-view-toggle-btn--explore'
                            : 'cu-view-toggle-btn'
                    }
                    onClick={handleViewToggle}
                    title={env.currentCamera === 'bird_eye'
                        ? t('controls.enterExploreView')
                        : t('controls.enterOverview')}
                    aria-label={env.currentCamera === 'bird_eye'
                        ? t('controls.enterExploreView')
                        : t('controls.enterOverview')}
                    aria-pressed={env.currentCamera !== 'bird_eye'}
                >
                    {env.currentCamera === 'bird_eye' ? (
                        <ViewToggleExploreIcon />
                    ) : (
                        <img
                            className="cu-view-toggle-icon cu-view-toggle-icon--overview"
                            src={toggleOverviewSvg}
                            alt=""
                            draggable={false}
                        />
                    )}
                    <span className="cu-view-toggle-label" aria-hidden="true">
                        {env.currentCamera === 'bird_eye'
                            ? t('controls.explore')
                            : t('controls.viewToggleOverview')}
                    </span>
                </button>
            )}

            {!hideCuChrome && isPeopleOpen && (
                <PeoplePanel
                    onClose={() => setIsPeopleOpen(false)}
                    overviewTimeOnly={env.currentCamera === 'bird_eye'}
                />
            )}

            {isMenuOpen && !hideCuChrome && (
                <ControlsMenu
                    onClose={closeMenu}
                    onOpenSettings={openSettingsPanel}
                    onSwitchToDevMode={switchToDevMode}
                />
            )}

            {isSettingsPanelOpen && !hideCuChrome && (
                <SettingsPanel
                    onClose={closeSettingsPanel}
                    onBackToMenu={closeSettingsAndOpenControlsMenu}
                />
            )}
        </div>
    );
};

export default CUControls;
export type { CUControlsSearchChipIntent } from './types';
