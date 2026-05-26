import React from 'react';
import { useTranslation } from 'react-i18next';
import PanelCloseButton from '../../../../cu/controls/PanelCloseButton';
import modeWalkIcon from '@icons/seat-navigation/PersonSimpleWalk.svg';
import modeWheelchairIcon from '@icons/seat-navigation/Wheelchair.svg';

interface CuBottomSheetProps {
    children: React.ReactNode;
    /** Focus-trap root — the fixed dock wrapping the sheet (WCAG keyboard). */
    rootRef?: React.RefObject<HTMLDivElement | null>;
    /** useBottomSheet return values */
    sheetShellRef: React.RefObject<HTMLDivElement>;
    handlebarHitRef: React.RefObject<HTMLDivElement>;
    sheetExiting: boolean;
    sheetEnterDone: boolean;
    sheetCollapsed: boolean;
    cuSheetShellStyle: React.CSSProperties | undefined;
    requestClose: () => void;
    onSheetShellAnimationEnd: (e: React.AnimationEvent<HTMLDivElement>) => void;
    onHandlePointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
    onHandlePointerMove: (e: React.PointerEvent<HTMLDivElement>) => void;
    finishHandlePull: (e: React.PointerEvent<HTMLDivElement>) => void;
    onHandlePointerCancel: (e: React.PointerEvent<HTMLDivElement>) => void;
    onHandleKeyDown: (e: React.KeyboardEvent<HTMLDivElement>) => void;
    /** Mode tabs */
    onNavmeshModeChange?: (mode: 'walking' | 'wheelchair') => void;
    cuTabMode: 'walking' | 'wheelchair';
    navmeshBaking: boolean;
    cuModeSwitchBusy: boolean;
    selectNavmeshTab: (mode: 'walking' | 'wheelchair') => void;
    cuInteractLocked: boolean;
    /** While stream overlay shows route controls — hide the pill handlebar */
    hideHandlebar?: boolean;
}

const CuBottomSheet: React.FC<CuBottomSheetProps> = ({
    children,
    rootRef,
    sheetShellRef,
    handlebarHitRef,
    sheetExiting,
    sheetEnterDone,
    sheetCollapsed,
    cuSheetShellStyle,
    requestClose,
    onSheetShellAnimationEnd,
    onHandlePointerDown,
    onHandlePointerMove,
    finishHandlePull,
    onHandlePointerCancel,
    onHandleKeyDown,
    onNavmeshModeChange,
    cuTabMode,
    navmeshBaking,
    cuModeSwitchBusy,
    selectNavmeshTab,
    cuInteractLocked,
    hideHandlebar = false,
}) => {
    const { t } = useTranslation();
    return (
    <div
        ref={rootRef}
        className={`cu-seat-panel__dock${sheetExiting ? ' cu-seat-panel__dock--exiting' : ''}`}
        aria-label={t('seat.findMySeat')}
        role="dialog"
        aria-modal="true"
    >
        <div
            ref={sheetShellRef}
            className={`cu-seat-panel__sheet-shell${sheetExiting ? ' cu-seat-panel__sheet-shell--exiting' : ''}`}
            style={cuSheetShellStyle}
            onAnimationEnd={onSheetShellAnimationEnd}
        >
            <div
                className={`cu-seat-panel__card cu-seat-panel__card--sheet${onNavmeshModeChange ? ' cu-seat-panel__card--with-navmesh-tabs' : ''}`}
            >
                <div
                    ref={handlebarHitRef}
                    hidden={hideHandlebar}
                    className={`cu-seat-panel__handlebar-hit${sheetEnterDone ? '' : ' cu-seat-panel__handlebar-hit--inactive'}`}
                    role="button"
                    tabIndex={hideHandlebar ? -1 : sheetEnterDone ? 0 : -1}
                    aria-expanded={!sheetCollapsed}
                    aria-label={sheetCollapsed ? t('seat.expandPanel') : t('seat.collapsePanel')}
                    onPointerDown={hideHandlebar ? undefined : onHandlePointerDown}
                    onPointerMove={hideHandlebar ? undefined : onHandlePointerMove}
                    onPointerUp={hideHandlebar ? undefined : finishHandlePull}
                    onPointerCancel={hideHandlebar ? undefined : onHandlePointerCancel}
                    onKeyDown={hideHandlebar ? undefined : onHandleKeyDown}
                >
                    <span className="cu-seat-panel__handlebar-pill" aria-hidden="true" />
                </div>
                <div className="cu-seat-panel__header-tabs">
                    <div className="cu-seat-panel__header">
                        <h2 className="cu-seat-panel__title">{t('seat.findMySeat')}</h2>
                        <PanelCloseButton
                            className="cu-seat-panel__close"
                            onClick={requestClose}
                        />
                    </div>
                    {onNavmeshModeChange && (
                        <div
                            className="cu-seat-panel__mode-tabs"
                            role="tablist"
                            aria-label={t('seat.navViewMode')}
                            aria-busy={navmeshBaking || cuModeSwitchBusy}
                        >
                            <button
                                type="button"
                                role="tab"
                                id="cu-seat-mode-standard"
                                aria-selected={cuTabMode === 'walking'}
                                disabled={navmeshBaking || cuModeSwitchBusy}
                                aria-disabled={navmeshBaking || cuModeSwitchBusy}
                                className={`cu-seat-panel__mode-tab${cuTabMode === 'walking' ? ' cu-seat-panel__mode-tab--active' : ''}`}
                                onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    selectNavmeshTab('walking');
                                }}
                            >
                                <img
                                    src={modeWalkIcon}
                                    alt=""
                                    className="cu-seat-panel__mode-tab-icon"
                                    width={20}
                                    height={20}
                                    draggable={false}
                                    aria-hidden={true}
                                />
                                {t('seat.byFoot')}
                            </button>
                            <button
                                type="button"
                                role="tab"
                                id="cu-seat-mode-wheelchair"
                                aria-selected={cuTabMode === 'wheelchair'}
                                disabled={navmeshBaking || cuModeSwitchBusy}
                                aria-disabled={navmeshBaking || cuModeSwitchBusy}
                                className={`cu-seat-panel__mode-tab${cuTabMode === 'wheelchair' ? ' cu-seat-panel__mode-tab--active' : ''}`}
                                onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    selectNavmeshTab('wheelchair');
                                }}
                            >
                                <img
                                    src={modeWheelchairIcon}
                                    alt=""
                                    className="cu-seat-panel__mode-tab-icon"
                                    width={20}
                                    height={20}
                                    draggable={false}
                                    aria-hidden={true}
                                />
                                {t('seat.wheelchair')}
                            </button>
                        </div>
                    )}
                </div>
                <div
                    className={`cu-seat-panel__body-wrap${cuInteractLocked ? ' cu-seat-panel__body-wrap--locked' : ''}`}
                    aria-disabled={cuInteractLocked ? true : undefined}
                >
                    {children}
                </div>
            </div>
        </div>
    </div>
    );
};

export default CuBottomSheet;
