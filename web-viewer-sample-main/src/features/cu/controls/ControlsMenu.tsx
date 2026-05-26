import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { flushSync } from 'react-dom';
import { CUControlsSearchChipIntent, ControlsMenuCardId } from '../types';
import {
    SEARCH_SUGGESTION_CHIPS,
    SEARCH_CHIP_FIND_SEAT,
    SEARCH_CHIP_FIND_TOILET,
    SEARCH_CHIP_FIND_QUIET,
} from '../constants';
import { useVoiceSearch } from '../hooks/useVoiceSearch';
import overviewMapGif from '../menu-icons/OverviewMap.gif';
import settingsMenuGif from '../menu-icons/Settings.gif';
import searchAssistantAvatarUrl from '@icons/search-bar/search-assistant-avatar.svg';
import searchBarSearchSvg from '@icons/search-bar/Search.svg';
import listSvg from '@icons/search-bar/List.svg';
import chatsSvg from '@icons/map-markers/Chats.svg';
import PanelCloseButton from './PanelCloseButton';
import { MicButton } from '../../../components/mic/MicButton';
import { useChat, useAppUI, useNavigation, useEnvironment } from '../../streaming/contexts';
import { useModalAccessibility } from '../../streaming/hooks/useModalAccessibility';
import { useSeatSheetForeground } from '../../streaming/hooks/useSeatSheetForeground';
import './ControlsMenu.css';

interface ControlsMenuProps {
    onClose: () => void;
    onOpenSettings: () => void;
    onSwitchToDevMode: () => void;
}

const ControlsMenu: React.FC<ControlsMenuProps> = ({
    onClose,
    onOpenSettings,
    onSwitchToDevMode,
}) => {
    const chat = useChat();
    const appUI = useAppUI();
    const nav = useNavigation();
    const env = useEnvironment();
    const onSearchChipNavigate = appUI.handleSearchChipNavigate;
    const onSendToAI = chat.handleSearchSendToAI;
    const hasActiveConversation = chat.conversation.hasConversation(chat.welcomeAvatarChatConfig.avatarId);
    const onOpenAssistantChat = chat.handleOpenAssistantChat;
    const lastAIResponseText = chat.lastAIResponseText;
    const lastAIResponseIsError = chat.lastAIResponseIsError ?? false;
    const aiTyping = chat.avatarAgentTyping;
    const { t } = useTranslation();
    const [searchText, setSearchText] = useState('');
    const [isSearchOverlayOpen, setIsSearchOverlayOpen] = useState(false);
    /** Stays set after chip click until menu closes, another chip is chosen, or seat sheet closes (seat intent). */
    const [activeSearchChipIntent, setActiveSearchChipIntent] = useState<CUControlsSearchChipIntent | null>(null);
    const prevSeatWidgetOpenRef = useRef(false);
    const [pressedCard, setPressedCard] = useState<ControlsMenuCardId | null>(null);
    const [explorePressedFlash, setExplorePressedFlash] = useState(false);
    const explorePressedFlashTimerRef = useRef<number | null>(null);
    const searchInputRef = useRef<HTMLInputElement>(null);
    const dialogRef = useRef<HTMLDivElement>(null);

    const voiceSearch = useVoiceSearch(setSearchText);

    const seatSheetForeground = useSeatSheetForeground();
    useModalAccessibility(dialogRef, { enabled: !seatSheetForeground });

    // Clear filter text when leaving search view
    useEffect(() => {
        if (!isSearchOverlayOpen) setSearchText('');
    }, [isSearchOverlayOpen]);

    // Escape closes search overlay
    useEffect(() => {
        if (!isSearchOverlayOpen) return;
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                setIsSearchOverlayOpen(false);
            }
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [isSearchOverlayOpen]);

    // Escape closes the whole ControlsMenu when no inner overlay handled it
    // first (WCAG 2.1.1 Keyboard / dialog dismissal pattern).
    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key !== 'Escape') return;
            // The search overlay handler above stops propagation, so by the time
            // we get here we know no inner overlay claimed the key press.
            if (isSearchOverlayOpen) return;
            onClose();
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [isSearchOverlayOpen, onClose]);

    // Stop voice recognition when search overlay closes
    useEffect(() => {
        if (!isSearchOverlayOpen) voiceSearch.cleanup();
    }, [isSearchOverlayOpen, voiceSearch]);

    useEffect(() => {
        return () => {
            if (explorePressedFlashTimerRef.current != null) {
                window.clearTimeout(explorePressedFlashTimerRef.current);
            }
        };
    }, []);

    useEffect(() => {
        const open = nav.seatWidgetOpen;
        if (
            activeSearchChipIntent === 'seat' &&
            prevSeatWidgetOpenRef.current &&
            !open
        ) {
            setActiveSearchChipIntent(null);
        }
        prevSeatWidgetOpenRef.current = open;
    }, [nav.seatWidgetOpen, activeSearchChipIntent]);

    const filteredChips = useMemo(() => {
        const q = searchText.trim().toLowerCase();
        if (!q) return SEARCH_SUGGESTION_CHIPS;
        return SEARCH_SUGGESTION_CHIPS.filter((c) => t(c.labelKey).toLowerCase().includes(q));
    }, [searchText, t]);

    const closeMenu = () => {
        setSearchText('');
        setIsSearchOverlayOpen(false);
        setActiveSearchChipIntent(null);
        setPressedCard(null);
        onClose();
    };

    const handleSearchChipClick = (chipLabelKey: string, intent: CUControlsSearchChipIntent) => {
        if (!onSearchChipNavigate) {
            setSearchText(t(chipLabelKey));
            return;
        }
        // Do not mirror the chip label into `searchText` — pressed styling uses `activeSearchChipIntent` + filter match.
        setSearchText('');
        setPressedCard(null);
        setActiveSearchChipIntent(intent);
        if (intent === 'seat') {
            // First-person: keep search + frosted controls visible so the seat
            // bottom sheet stacks above (see SeatNavigateWidget.css z-index).
            // Bird-eye: close the search overlay so the bird-eye seat-directions
            // panel + map polyline are visible.
            if (env.currentCamera === 'bird_eye') {
                setIsSearchOverlayOpen(false);
                onClose();
            }
            onSearchChipNavigate(intent);
            return;
        }
        setIsSearchOverlayOpen(false);
        onClose();
        onSearchChipNavigate(intent);
    };

    const handleExploreClick = () => {
        if (explorePressedFlashTimerRef.current != null) {
            window.clearTimeout(explorePressedFlashTimerRef.current);
        }
        setExplorePressedFlash(true);
        explorePressedFlashTimerRef.current = window.setTimeout(() => {
            setExplorePressedFlash(false);
            explorePressedFlashTimerRef.current = null;
        }, 220);

        closeMenu();
    };

    const handleDockSearchInputFocus = () => {
        if (isSearchOverlayOpen) return;
        flushSync(() => setIsSearchOverlayOpen(true));
        queueMicrotask(() => searchInputRef.current?.focus({ preventScroll: true }));
    };

    const submitDockSearch = () => {
        const q = searchText.trim();
        if (!q) return;
        if (!isSearchOverlayOpen) {
            flushSync(() => setIsSearchOverlayOpen(true));
        }
        onSendToAI?.(q);
        setSearchText('');
        queueMicrotask(() => searchInputRef.current?.blur());
    };

    const handleDockSendClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        submitDockSearch();
    };

    const dockSearchHasText = searchText.trim().length > 0;

    return (
        <div
            ref={dialogRef}
            id="cu-controls-menu-dialog"
            className="cu-controls-menu-frost"
            role="dialog"
            aria-modal="true"
            aria-label={isSearchOverlayOpen ? t('common.search') : t('controls.controls')}
            aria-hidden={seatSheetForeground ? true : undefined}
            inert={seatSheetForeground ? true : undefined}
            onClick={closeMenu}
        >
            {isSearchOverlayOpen ? (
                <button
                    type="button"
                    className="cu-hamburger cu-controls-menu-frost-hamburger"
                    title={t('settings.backToQuickActions')}
                    aria-label={t('controls.backCloseSearch')}
                    onClick={(e) => {
                        e.stopPropagation();
                        setIsSearchOverlayOpen(false);
                    }}
                >
                    <img src={listSvg} alt="" className="cu-hamburger-icon" />
                </button>
            ) : (
                <PanelCloseButton
                    className="cu-controls-menu-x"
                    onClick={(e) => {
                        e.stopPropagation();
                        closeMenu();
                    }}
                />
            )}

            {!isSearchOverlayOpen && (
                <div
                    className="cu-controls-menu-body"
                    onClick={(e) => e.stopPropagation()}
                >
                    <div
                        className="cu-controls-menu-actions"
                        role="group"
                        aria-label={t('controls.quickActions')}
                    >
                        <button
                            type="button"
                            className={`cu-figma-action-btn cu-figma-action-btn--featured ${
                                explorePressedFlash ? 'cu-figma-action-btn--pressed' : ''
                            }`}
                            title={t('controls.explore')}
                            aria-label={t('controls.exploreDescription')}
                            onClick={handleExploreClick}
                        >
                            <div className="cu-figma-action-btn-row">
                                <span className="cu-figma-action-btn-icon-wrap cu-figma-action-btn-icon-wrap--featured">
                                    <img
                                        className="cu-figma-action-btn-gif cu-figma-action-btn-gif--featured"
                                        src={overviewMapGif}
                                        alt=""
                                        width={96}
                                        height={96}
                                        draggable={false}
                                    />
                                </span>
                                <span className="cu-figma-action-btn-text-stack">
                                    <span className="cu-figma-action-btn-title">{t('controls.explore')}</span>
                                    <span className="cu-figma-action-btn-sub">{t('controls.visitVirtually')}</span>
                                </span>
                            </div>
                        </button>
                        <button
                            type="button"
                            className="cu-figma-action-btn cu-figma-action-btn--featured"
                            title={t('controls.settingsTitle')}
                            aria-label={t('controls.settingsDescription')}
                            onClick={onOpenSettings}
                        >
                            <div className="cu-figma-action-btn-row">
                                <span className="cu-figma-action-btn-icon-wrap cu-figma-action-btn-icon-wrap--featured">
                                    <img
                                        className="cu-figma-action-btn-gif cu-figma-action-btn-gif--featured"
                                        src={settingsMenuGif}
                                        alt=""
                                        width={96}
                                        height={96}
                                        draggable={false}
                                    />
                                </span>
                                <span className="cu-figma-action-btn-text-stack">
                                    <span className="cu-figma-action-btn-title">{t('controls.settingsTitle')}</span>
                                    <span className="cu-figma-action-btn-sub">
                                        {t('controls.settingsSubtitle')}
                                    </span>
                                </span>
                            </div>
                        </button>
                        <button
                            type="button"
                            className="cu-figma-action-btn cu-figma-action-btn--dev-chip"
                            title={t('controls.devMode')}
                            aria-label={t('controls.devModeDescription')}
                            onClick={onSwitchToDevMode}
                        >
                            <span className="cu-figma-action-btn-text-stack cu-figma-action-btn-text-stack--dev-chip">
                                <span className="cu-figma-action-btn-title">{t('controls.devMode')}</span>
                                <span className="cu-figma-action-btn-sub">{t('controls.toolsDebug')}</span>
                            </span>
                        </button>
                    </div>
                </div>
            )}

            {isSearchOverlayOpen && (
                <div
                    className="cu-controls-search-panel"
                    role="region"
                    aria-labelledby="cu-controls-search-panel-heading"
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="cu-controls-search-panel-inner">
                        <h2
                            className="cu-controls-search-panel-title"
                            id="cu-controls-search-panel-heading"
                        >
                            {t('common.search')}
                        </h2>
                    </div>

                    {(hasActiveConversation || aiTyping) && (
                        <div className="cu-controls-search-assistant-strip">
                            <div className="cu-controls-search-assistant" aria-label={t('controls.assistant')}>
                                <blockquote className="cu-controls-search-assistant-bubble">
                                    <div
                                        className="cu-controls-search-assistant-avatar cu-controls-search-assistant-avatar--in-bubble"
                                        aria-hidden="true"
                                    >
                                        <img
                                            src={searchAssistantAvatarUrl}
                                            alt=""
                                            width={56}
                                            height={56}
                                            decoding="async"
                                            draggable={false}
                                            className="cu-controls-search-assistant-avatar-img"
                                        />
                                    </div>
                                    <div className="cu-controls-search-assistant-bubble-main">
                                        {aiTyping ? (
                                            <div className="cu-controls-search-typing-indicator">
                                                <span className="cu-controls-search-typing-dot" />
                                                <span className="cu-controls-search-typing-dot" />
                                                <span className="cu-controls-search-typing-dot" />
                                            </div>
                                        ) : (
                                            <p
                                                className={`cu-controls-search-assistant-bubble-text${lastAIResponseText && lastAIResponseIsError ? ' cu-controls-search-assistant-bubble-text--error' : ''}`}
                                                role="status"
                                                aria-live="polite"
                                                aria-atomic="true"
                                            >
                                                {lastAIResponseText || t('controls.continueConversation')}
                                            </p>
                                        )}
                                        {!aiTyping ? (
                                            <button
                                                type="button"
                                                className="cu-controls-search-assistant-open-chat"
                                                title={t('controls.openChatWithAssistant')}
                                                aria-label={t('controls.openChat')}
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    onOpenAssistantChat();
                                                }}
                                            >
                                                <span
                                                    className="cu-controls-search-assistant-open-chat-icon"
                                                    aria-hidden="true"
                                                >
                                                    <img
                                                        src={chatsSvg}
                                                        alt=""
                                                        width={16}
                                                        height={16}
                                                        draggable={false}
                                                        className="cu-controls-search-assistant-open-chat-img"
                                                    />
                                                </span>
                                                <span className="cu-controls-search-assistant-open-chat-label">
                                                    {t('controls.openChat')}
                                                </span>
                                            </button>
                                        ) : null}
                                    </div>
                                </blockquote>
                            </div>
                        </div>
                    )}

                    <section className="cu-controls-search-section">
                        <div
                            className="cu-controls-search-chips"
                            role="group"
                            aria-label={t('controls.searchSuggestions')}
                        >
                            {filteredChips.length === 0 ? (
                                <p className="cu-controls-search-chips-empty" role="status">
                                    {t('controls.noMatchingSuggestions')}
                                </p>
                            ) : (
                                filteredChips.map((chip) => {
                                    const filterMatchesChip =
                                        searchText.trim().toLowerCase() ===
                                        t(chip.labelKey).trim().toLowerCase();
                                    const chipPressed =
                                        filterMatchesChip || activeSearchChipIntent === chip.intent;
                                    return (
                                        <button
                                            key={chip.labelKey}
                                            type="button"
                                            aria-pressed={chipPressed}
                                            className={`cu-controls-search-chip${
                                                chip.labelKey === SEARCH_CHIP_FIND_SEAT
                                                    ? ' cu-controls-search-chip--find-seat'
                                                    : chip.labelKey === SEARCH_CHIP_FIND_TOILET
                                                        ? ' cu-controls-search-chip--toilet'
                                                        : chip.labelKey === SEARCH_CHIP_FIND_QUIET
                                                            ? ' cu-controls-search-chip--quiet'
                                                            : ''
                                            }${chipPressed ? ' cu-controls-search-chip--pressed' : ''}${
                                                chip.comingSoon ? ' cu-controls-search-chip--coming-soon' : ''
                                            }`}
                                            disabled={chip.comingSoon}
                                            onClick={() => handleSearchChipClick(chip.labelKey, chip.intent)}
                                        >
                                            <span
                                                className="cu-controls-search-chip-icon"
                                                style={{ backgroundImage: `url(${chip.icon})` }}
                                                aria-hidden
                                            />
                                            <span className="cu-controls-search-chip-label">{t(chip.labelKey)}</span>
                                        </button>
                                    );
                                })
                            )}
                        </div>
                    </section>
                </div>
            )}

            <div
                className="cu-controls-menu-search-dock"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="cu-controls-menu-search-shell">
                    <div className="cu-controls-menu-search-inner cu-controls-menu-search-inner--collapsed">
                        <form
                            className="cu-controls-menu-search-field-row"
                            role="search"
                            onClick={(e) => e.stopPropagation()}
                            onSubmit={(e) => {
                                e.preventDefault();
                                if (searchText.trim()) submitDockSearch();
                            }}
                        >
                            <img
                                src={searchBarSearchSvg}
                                alt=""
                                width={20}
                                height={20}
                                draggable={false}
                                className="cu-controls-menu-search-edge-img"
                                aria-hidden
                            />
                            <input
                                ref={searchInputRef}
                                id="cu-controls-search-filter-input"
                                name="cu-controls-search"
                                type="search"
                                className="cu-controls-menu-search-filter-input"
                                placeholder={t('controls.searchPlaceholder')}
                                aria-label={t('common.search')}
                                autoComplete="search"
                                autoCorrect="off"
                                autoCapitalize="none"
                                spellCheck={false}
                                value={searchText}
                                onChange={(e) => setSearchText(e.target.value)}
                                onFocus={handleDockSearchInputFocus}
                                onClick={(e) => e.stopPropagation()}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        e.preventDefault();
                                        if (searchText.trim()) submitDockSearch();
                                    }
                                }}
                            />
                        </form>
                    </div>
                    {dockSearchHasText ? (
                        <button
                            type="button"
                            className="cu-controls-menu-search-edge-btn cu-controls-menu-search-send-btn"
                            title={t('common.send')}
                            aria-label={t('controls.sendSearch')}
                            onMouseDown={(e) => {
                                e.preventDefault();
                            }}
                            onClick={handleDockSendClick}
                        >
                            <svg
                                className="cu-controls-menu-search-send-icon"
                                viewBox="0 0 23 23"
                                fill="none"
                                xmlns="http://www.w3.org/2000/svg"
                                aria-hidden
                            >
                                <path
                                    d="M21.563 11.4905C21.5636 11.7466 21.4958 11.9983 21.3666 12.2194C21.2374 12.4406 21.0515 12.6232 20.828 12.7483L5.74112 21.3744C5.52462 21.4972 5.2802 21.5621 5.03134 21.5631C4.80204 21.5619 4.57637 21.5058 4.37316 21.3996C4.16994 21.2934 3.99509 21.1401 3.86319 20.9525C3.73128 20.765 3.64616 20.5486 3.61493 20.3214C3.5837 20.0942 3.60726 19.8629 3.68365 19.6467L6.10949 12.4635C6.1332 12.3933 6.17804 12.3321 6.23787 12.2884C6.29771 12.2446 6.3696 12.2204 6.44371 12.2191H12.9378C13.0363 12.2194 13.1338 12.1993 13.2243 12.1603C13.3148 12.1212 13.3962 12.0639 13.4636 11.9921C13.531 11.9202 13.5829 11.8352 13.6161 11.7425C13.6493 11.6497 13.6631 11.5511 13.6565 11.4528C13.6402 11.2679 13.5547 11.0961 13.4171 10.9716C13.2795 10.8472 13.0999 10.7793 12.9144 10.7816H6.44551C6.37032 10.7816 6.29703 10.758 6.23594 10.7142C6.17485 10.6704 6.12906 10.6085 6.105 10.5372L3.67916 3.35495C3.5826 3.07966 3.5721 2.7815 3.64903 2.5001C3.72596 2.21869 3.88669 1.96735 4.10987 1.77946C4.33305 1.59158 4.60812 1.47604 4.89852 1.44821C5.18892 1.42037 5.48092 1.48156 5.73573 1.62363L20.8298 10.2389C21.052 10.3638 21.237 10.5455 21.3658 10.7655C21.4946 10.9854 21.5627 11.2356 21.563 11.4905Z"
                                    fill="currentColor"
                                />
                            </svg>
                        </button>
                    ) : (
                        <MicButton
                            className="cu-controls-menu-search-mic"
                            title={voiceSearch.isListening
                                ? t('controls.voiceSearchListening')
                                : t('controls.voiceSearchHold')}
                            aria-label={voiceSearch.isListening
                                ? t('controls.voiceSearchListening')
                                : t('controls.voiceSearchHold')}
                            pressed={voiceSearch.isListening}
                            onPointerDown={(e) => {
                                if (e.pointerType === '') return;
                                e.preventDefault();
                                e.stopPropagation();
                                if (!isSearchOverlayOpen) {
                                    flushSync(() => setIsSearchOverlayOpen(true));
                                    queueMicrotask(() => voiceSearch.start());
                                } else {
                                    voiceSearch.start();
                                }
                            }}
                            onPointerUp={(e) => {
                                if (e.pointerType === '') return;
                                e.preventDefault();
                                e.stopPropagation();
                                voiceSearch.stop();
                            }}
                            onPointerCancel={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                voiceSearch.stop();
                            }}
                            onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                if (e.detail === 0) {
                                    if (!isSearchOverlayOpen) {
                                        flushSync(() => setIsSearchOverlayOpen(true));
                                        queueMicrotask(() => voiceSearch.toggle());
                                    } else {
                                        voiceSearch.toggle();
                                    }
                                }
                            }}
                        />
                    )}
                </div>
            </div>
        </div>
    );
};

export default ControlsMenu;
