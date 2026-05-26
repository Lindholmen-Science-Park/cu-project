import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { flushSync } from 'react-dom';
import './AvatarChatOverlay.css';
import { MicButton } from '../../../../components/mic/MicButton';
import avatarChatSendDarkSvg from '@icons/chat/Send-dark.svg';
import cuListSvg from '@icons/search-bar/List.svg';
import PanelCloseButton from '../../../cu/controls/PanelCloseButton';
import { useDocumentDarkMode } from '../../../cu/hooks/useDocumentDarkMode';
import { useVisualViewportInsets } from '../../hooks/useVisualViewportInsets';
import { useModalAccessibility } from '../../hooks/useModalAccessibility';
import { useChat, useControl } from '../../contexts';
import { sendMessage } from '../../messaging';
import {
    speakText,
    type AvatarVoiceProfile,
    type SpeechController,
} from '../../../../services/speechSynthesis';
import redAvatarImageUrl from '../../../../../../kit-app-template-main/source/data/Assets/Avatars/red_image.png';
import TtsSpeakerIcon from '../TtsSpeakerIcon';

const MAX_WORD_LENGTH = 60;
function truncateLongWords(text: string): string {
    return text.replace(/\S+/g, (word) =>
        word.length > MAX_WORD_LENGTH ? word.slice(0, MAX_WORD_LENGTH) + '\u2026' : word
    );
}

const avatarModules: Record<string, string> = {};
const rawModules = import.meta.glob(
    '../../../../../../kit-app-template-main/source/data/Assets/Avatars/*.{png,jpg,webp,svg}',
    { eager: true, import: 'default' },
);
for (const [path, url] of Object.entries(rawModules)) {
    const filename = path.split('/').pop();
    if (filename) avatarModules[filename] = url as string;
}

function resolveAvatarImage(filename: string | undefined): string | undefined {
    if (!filename) return undefined;
    return avatarModules[filename];
}

const chatBgModules: Record<string, string> = {};
const rawChatBgModules = import.meta.glob('../../../../icons/chat/backgrounds/*.{png,jpg,webp,svg}', {
    eager: true,
    import: 'default',
});
for (const [path, url] of Object.entries(rawChatBgModules)) {
    const filename = path.split('/').pop();
    if (filename) chatBgModules[filename] = url as string;
}

function resolveChatBackgroundImage(filename: string | undefined): string | undefined {
    if (!filename) return undefined;
    return chatBgModules[filename];
}

/** 32×32 Figma portrait: Lemon fill + circular clip (same structure as exported SVG, uses bundled PNG URL). */
const AvatarPortrait = React.forwardRef<HTMLSpanElement, { src: string; alt: string }>(
    function AvatarPortrait({ src, alt }, ref) {
        const clipId = React.useId().replace(/:/g, '');
        return (
            <span
                ref={ref}
                className="avatar-chat-portrait"
                role="img"
                aria-label={alt}
                tabIndex={-1}
            >
                <svg
                    width={32}
                    height={32}
                    viewBox="0 0 32 32"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    xmlnsXlink="http://www.w3.org/1999/xlink"
                    aria-hidden
                    focusable="false"
                    className="avatar-chat-portrait-svg"
                >
                    <defs>
                        <clipPath id={clipId}>
                            <circle cx={16} cy={16} r={16} />
                        </clipPath>
                    </defs>
                    <circle cx={16} cy={16} r={16} fill="#DCFF7D" />
                    <g clipPath={`url(#${clipId})`}>
                        {/* Figma: bg-size 163.125% 163.125%, position -9.8px 0 — 32 * 1.63125 ≈ 52.2 */}
                        <image
                            href={src}
                            x={-9.8}
                            y={0}
                            width={52.2}
                            height={52.2}
                            preserveAspectRatio="xMidYMid slice"
                        />
                    </g>
                </svg>
            </span>
        );
    },
);


export interface QuickAction {
    id: string;
    label: string;
}

export interface AvatarChatMessage {
    role: 'user' | 'assistant';
    text: string;
    quickActions?: QuickAction[];
    isError?: boolean;
    /**
     * BCP-47 language tag of `text`. Set this when the message text isn't in
     * the UI language — currently only AI replies in fr/es UIs, where the AI
     * backend forces en/sv (see {@link aiLanguageFor}). Used by the "Listen"
     * button so a French UI doesn't try to pronounce English text with a
     * French voice. When unset, the listen button assumes the message is in
     * the current UI language.
     */
    lang?: string;
}

export interface AvatarChatConfig {
    avatarId: string;
    avatarName: string;
    avatarImage?: string;
    greeting: string;
    quickActions?: QuickAction[];
    /** USD prim path of the NPC in the scene (e.g. "/World/Red"). Used to hide the 3D avatar while the chat overlay is open. */
    primPath?: string;
    /** Full-body character image shown behind the chat when opened from NPC click (not search). Per-avatar so each NPC can have its own. */
    chatBackgroundImage?: string;
    /**
     * Per-character voice settings for the "Listen" buttons. Keeps a given
     * avatar consistent across UI languages (e.g. Red sounds female in both
     * English and Swedish). Sourced from `interactions.json`'s `npcConfig.voice`
     * on the Kit side — when omitted, the shared TTS layer falls back to the
     * neutral profile (OS default voice for the spoken language).
     */
    voiceProfile?: AvatarVoiceProfile;
}

const AvatarChatOverlayInner: React.FC = () => {
    const ctrl = useControl();
    const chat = useChat();
    const config = ctrl.avatarChatConfig!;
    const onClose = chat.handleChatClose;
    const onBack = chat.handleChatBack;
    const onSend = chat.handleChatSend;
    const onQuickAction = chat.handleChatQuickAction;
    const externalMessages = chat.conversation.getMessages(config.avatarId);
    const onUserMessage = chat.handleChatUserMessage;
    const typing = chat.avatarAgentTyping;
    const hideBackdrop = chat.chatOpenSource === 'search';
    const showCharacterBackground = chat.chatOpenSource === 'npc';
    const { t, i18n } = useTranslation();
    const [input, setInput] = useState('');
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const messagesContainerRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const overlayRootRef = useRef<HTMLDivElement>(null);
    const sheetRef = useRef<HTMLDivElement>(null);
    const greetingSeeded = useRef(false);
    const avatarFocusRef = useRef<HTMLSpanElement>(null);
    useModalAccessibility(overlayRootRef);
    const previouslyFocusedRef = useRef<HTMLElement | null>(null);
    const speechControllerRef = useRef<SpeechController | null>(null);
    const avatarMicRecognitionRef = useRef<{ stop: () => void } | null>(null);
    const avatarMicStreamRef = useRef<MediaStream | null>(null);
    const [avatarMicRecording, setAvatarMicRecording] = useState(false);
    const [ttsPlayingMessageIndex, setTtsPlayingMessageIndex] = useState<number | null>(null);
    const isDarkMode = useDocumentDarkMode();
    const visualViewport = useVisualViewportInsets();
    const fixedViewportStyle = useMemo(
        () => ({
            top: visualViewport.top,
            left: visualViewport.left,
            width: visualViewport.width,
            height: visualViewport.height,
        }),
        [visualViewport.top, visualViewport.left, visualViewport.width, visualViewport.height],
    );
    /** Dark mode: Lemon press — luokka + flushSync, ei pelkkä :active (selain voi jättää :active jumiin). */
    const [pressedQuickActionId, setPressedQuickActionId] = useState<string | null>(null);

    const avatarImgUrl = resolveAvatarImage(config.avatarImage) ?? redAvatarImageUrl;
    const chatBgUrl = showCharacterBackground
        ? resolveChatBackgroundImage(config.chatBackgroundImage)
        : undefined;
    const normalizedGreeting = String(config.greeting || '').trim() || t('interactions.avatar_red.greeting');

    // Seed the greeting into the store if this avatar has no messages yet.
    useEffect(() => {
        if (greetingSeeded.current) return;
        if (!externalMessages || externalMessages.length === 0) {
            greetingSeeded.current = true;
            onUserMessage?.({
                role: 'assistant',
                text: normalizedGreeting,
                quickActions: config.quickActions,
            });
        }
    }, [externalMessages, normalizedGreeting, config.quickActions, onUserMessage]);

    const rawMessages = externalMessages ?? [];

    // Always reflect the current language for the initial greeting and quick actions.
    // The conversation store keeps the original seeded text, but we override the
    // first assistant message so a language switch takes effect immediately.
    const messages = useMemo(() => {
        if (!rawMessages.length) return rawMessages;
        const first = rawMessages[0];
        if (first.role !== 'assistant') return rawMessages;
        return [
            { ...first, text: normalizedGreeting, quickActions: config.quickActions },
            ...rawMessages.slice(1),
        ];
    }, [rawMessages, normalizedGreeting, config.quickActions]);

    const mountedRef = useRef(false);

    const scrollToBottom = (instant: boolean) => {
        const el = messagesContainerRef.current;
        if (el) el.scrollTop = el.scrollHeight;
        else messagesEndRef.current?.scrollIntoView({ behavior: instant ? 'instant' : 'smooth' });
    };

    // Show scrollbar only while user is actively scrolling
    const scrollTimerRef = useRef<ReturnType<typeof setTimeout>>();
    const handleScroll = useCallback(() => {
        messagesContainerRef.current?.classList.add('is-scrolling');
        clearTimeout(scrollTimerRef.current);
        scrollTimerRef.current = setTimeout(() => {
            messagesContainerRef.current?.classList.remove('is-scrolling');
        }, 800);
    }, []);

    useEffect(() => {
        const el = messagesContainerRef.current;
        if (!el) return;
        el.addEventListener('scroll', handleScroll, { passive: true });
        return () => {
            el.removeEventListener('scroll', handleScroll);
            clearTimeout(scrollTimerRef.current);
        };
    }, [handleScroll]);

    // On mount: force scroll to bottom after layout settles
    useEffect(() => {
        const t = setTimeout(() => scrollToBottom(true), 80);
        return () => clearTimeout(t);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        if (!mountedRef.current) {
            mountedRef.current = true;
            scrollToBottom(true);
        } else {
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, typing]);

    // Shrink-wrap user bubbles to the width of their longest wrapped line
    useLayoutEffect(() => {
        const container = messagesContainerRef.current;
        if (!container) return;

        container
            .querySelectorAll<HTMLElement>('.avatar-chat-msg.user .avatar-chat-bubble')
            .forEach((el) => {
                el.style.width = '';
                const textNode = Array.from(el.childNodes).find(
                    (n) => n.nodeType === Node.TEXT_NODE && n.textContent?.trim()
                );
                if (!textNode) return;

                const range = document.createRange();
                range.selectNodeContents(textNode);
                const rects = Array.from(range.getClientRects()).filter((r) => r.width > 0);
                if (rects.length <= 1) return;

                const maxLine = Math.max(...rects.map((r) => r.width));
                const cs = getComputedStyle(el);
                const pad =
                    (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
                const border =
                    (parseFloat(cs.borderLeftWidth) || 0) + (parseFloat(cs.borderRightWidth) || 0);
                el.style.width = `${Math.ceil(maxLine + pad + border + 2)}px`;
            });
    }, [messages, typing]);

    useEffect(() => {
        // WCAG 2.4.3 (Focus Order) + APG dialog pattern: remember the element
        // that opened the chat so we can restore focus to it on close.
        previouslyFocusedRef.current =
            (document.activeElement as HTMLElement | null) ?? null;
        // Opening focus: chrome (back/close) first so Tab reaches header controls before messages.
        requestAnimationFrame(() => {
            const root = overlayRootRef.current;
            const chrome =
                root?.querySelector<HTMLElement>('.avatar-chat-back-btn') ??
                root?.querySelector<HTMLElement>('.avatar-chat-close-btn, .cu-panel-close-btn');
            if (chrome) {
                chrome.focus({ preventScroll: true });
                return;
            }
            inputRef.current?.focus({ preventScroll: true });
        });
        sendMessage('movementInputControl', { enabled: false });
        return () => {
            sendMessage('movementInputControl', { enabled: true });
            const opener = previouslyFocusedRef.current;
            if (opener && document.body.contains(opener)) {
                try { opener.focus({ preventScroll: true }); } catch { opener.focus(); }
            }
        };
    }, []);

    const handleDismiss = onBack ?? onClose;

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') handleDismiss();
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [handleDismiss]);

    useEffect(() => {
        // Cancel any in-flight utterance when the overlay unmounts.
        return () => {
            speechControllerRef.current?.cancel();
            speechControllerRef.current = null;
        };
    }, []);

    const startAvatarVoiceInput = useCallback(async () => {
        if (typeof window === 'undefined') return;
        type RecInstance = {
            lang: string;
            interimResults: boolean;
            continuous?: boolean;
            maxAlternatives: number;
            onresult: ((ev: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null;
            onerror: (() => void) | null;
            onend: (() => void) | null;
            start: () => void;
            stop: () => void;
        };
        type RecCtor = new () => RecInstance;
        const w = window as typeof window & {
            SpeechRecognition?: RecCtor;
            webkitSpeechRecognition?: RecCtor;
        };
        const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
        if (!Ctor) return;

        if (navigator.mediaDevices?.getUserMedia) {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                avatarMicStreamRef.current = stream;
            } catch {
                // Continue anyway: some browsers handle mic permission inside SpeechRecognition.
                avatarMicStreamRef.current = null;
            }
        }

        try { avatarMicRecognitionRef.current?.stop(); } catch {}
        try {
            const rec = new Ctor();
            rec.lang = /^fi/i.test(navigator.language || '') ? 'fi-FI' : 'en-US';
            rec.interimResults = true;
            rec.continuous = true;
            rec.maxAlternatives = 1;
            rec.onresult = (event: any) => {
                const results = event?.results;
                if (!results) return;
                let text = '';
                for (let i = 0; i < results.length; i++) {
                    const alt = results[i]?.[0];
                    if (!alt?.transcript) continue;
                    text += `${alt.transcript} `;
                }
                const normalized = text.trim();
                if (normalized) setInput(normalized);
            };
            rec.onerror = () => { avatarMicRecognitionRef.current = null; };
            rec.onend = () => {
                avatarMicRecognitionRef.current = null;
                setAvatarMicRecording(false);
            };
            avatarMicRecognitionRef.current = rec;
            rec.start();
            setAvatarMicRecording(true);
        } catch {
            avatarMicRecognitionRef.current = null;
            setAvatarMicRecording(false);
        }
    }, []);

    const stopAvatarVoiceInput = useCallback(() => {
        try { avatarMicRecognitionRef.current?.stop(); } catch {}
        setAvatarMicRecording(false);
        const stream = avatarMicStreamRef.current;
        if (stream) {
            stream.getTracks().forEach((t) => t.stop());
            avatarMicStreamRef.current = null;
        }
    }, []);

    useEffect(() => () => {
        try { avatarMicRecognitionRef.current?.stop(); } catch {}
        const stream = avatarMicStreamRef.current;
        if (stream) {
            stream.getTracks().forEach((t) => t.stop());
            avatarMicStreamRef.current = null;
        }
    }, []);

    const handleSend = () => {
        const text = input.trim();
        if (!text) return;
        onUserMessage?.({ role: 'user', text });
        setInput('');
        onSend?.(text);
        inputRef.current?.focus();
    };

    const canSend = input.trim().length > 0;

    const handleQuickAction = (actionId: string, label: string) => {
        onUserMessage?.({ role: 'user', text: label });
        onQuickAction?.(actionId);
    };

    const handleBackdropClick = (e: React.MouseEvent) => {
        if (hideBackdrop) return;
        if (sheetRef.current && !sheetRef.current.contains(e.target as Node)) {
            onClose();
        }
    };

    const showPortrait = (index: number): boolean => {
        if (messages[index]?.role !== 'assistant') return false;
        const next = messages[index + 1];
        return !next || next.role !== 'assistant';
    };

    const handleListenClick = (text: string, messageIndex: number, msgLang?: string) => {
        if (ttsPlayingMessageIndex === messageIndex) {
            speechControllerRef.current?.cancel();
            speechControllerRef.current = null;
            setTtsPlayingMessageIndex(null);
            return;
        }
        speechControllerRef.current?.cancel();
        const plain = text.replace(/\s*\n+\s*/g, ' ').trim();
        if (!plain) return;
        // Voice language must match the language of the *text*, not the UI:
        // AI replies in fr/es UIs come back in English (backend doesn't yet
        // support those locales), so pronouncing them with a French voice
        // would mangle the words. Fall back to UI language for everything
        // else (i18n greetings, user input, quick-action labels).
        speechControllerRef.current = speakText(plain, {
            uiLang: msgLang ?? i18n.language,
            voiceProfile: config.voiceProfile,
            onStart: () => setTtsPlayingMessageIndex(messageIndex),
            onEnd: () => setTtsPlayingMessageIndex(null),
            onError: () => setTtsPlayingMessageIndex(null),
        });
    };

    const keyboardOpenClass = visualViewport.keyboardLikelyOpen
        ? ' avatar-chat--keyboard-open'
        : '';

    return (
        <div ref={overlayRootRef} className="avatar-chat-overlay-root">
            <div
                className={`avatar-chat-backdrop${hideBackdrop ? ' avatar-chat-backdrop--solid' : ''}${keyboardOpenClass}`}
                style={fixedViewportStyle}
                onClick={handleBackdropClick}
            />
            {chatBgUrl && (
                <div
                    className={`avatar-chat-character-bg${keyboardOpenClass}`}
                    style={fixedViewportStyle}
                    aria-hidden="true"
                >
                    <img
                        src={chatBgUrl}
                        alt=""
                        className="avatar-chat-character-bg__img"
                        draggable={false}
                    />
                </div>
            )}
            {onBack && (
                <>
                    <button
                        type="button"
                        className="avatar-chat-back-btn"
                        onClick={onBack}
                        aria-label={t('avatar.backToSearch')}
                        title={t('avatar.back')}
                    >
                        <svg width={18} height={18} viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
                            <path d="M11.25 4.5L6.75 9L11.25 13.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                    </button>
                    <button
                        type="button"
                        className="avatar-chat-hamburger-btn"
                        onClick={() => {
                            onBack();
                            setTimeout(() =>
                                window.dispatchEvent(new Event('cu-controls-reopen-menu')), 120
                            );
                        }}
                        aria-label={t('controls.openControls')}
                        title={t('controls.openControls')}
                    >
                        <img src={cuListSvg} alt="" className="avatar-chat-hamburger-icon" draggable={false} />
                    </button>
                </>
            )}
            {!onBack && (
                <PanelCloseButton
                    className="avatar-chat-close-btn"
                    onClick={onClose}
                />
            )}
            <div
                className={`avatar-chat-container${hideBackdrop ? ' avatar-chat-container--above-controls' : ''}${keyboardOpenClass}`}
                style={fixedViewportStyle}
                onClick={handleBackdropClick}
            >
                <div
                    ref={sheetRef}
                    className="avatar-chat-sheet"
                    tabIndex={-1}
                    onClick={e => e.stopPropagation()}
                    onKeyDown={e => e.stopPropagation()}
                    onKeyUp={e => e.stopPropagation()}
                >
                    <div className={`avatar-chat-panel${showCharacterBackground ? ' avatar-chat-panel--with-character' : ''}`}>
                        <div ref={messagesContainerRef} className="avatar-chat-messages">
                            <div className="avatar-chat-messages-spacer" />
                            {messages.map((m, i) => (
                                <div key={i} className={`avatar-chat-msg ${m.role}`}>
                                    {m.role === 'assistant' && showPortrait(i) && avatarImgUrl ? (
                                        <AvatarPortrait
                                            ref={i === 0 ? avatarFocusRef : undefined}
                                            src={avatarImgUrl}
                                            alt={config.avatarName}
                                        />
                                    ) : m.role === 'assistant' ? (
                                        <div className="avatar-chat-portrait-spacer" />
                                    ) : null}
                                    <div className="avatar-chat-msg-body">
                                        <div className={`avatar-chat-bubble${m.isError ? ' avatar-chat-bubble--error' : ''}`}>
                                            {m.role === 'assistant' ? (
                                                <>
                                                    <div className="avatar-chat-bubble-head">
                                                        <p className="avatar-chat-bubble-text">{m.text}</p>
                                                        {!m.isError && (
                                                            <button
                                                                type="button"
                                                                className={`avatar-chat-speaker ${
                                                                    ttsPlayingMessageIndex === i
                                                                        ? 'avatar-chat-speaker--playing'
                                                                        : ''
                                                                }`}
                                                                title={t('avatar.listen')}
                                                                aria-label={t('avatar.listen')}
                                                                aria-pressed={ttsPlayingMessageIndex === i}
                                                                onClick={() => handleListenClick(m.text, i, m.lang)}
                                                            >
                                                                <TtsSpeakerIcon className="avatar-chat-speaker-icon" />
                                                            </button>
                                                        )}
                                                    </div>
                                                    {m.quickActions && m.quickActions.length > 0 ? (
                                                        <div className="avatar-chat-actions avatar-chat-actions--in-bubble">
                                                            {m.quickActions.map(qa => (
                                                                <button
                                                                    key={qa.id}
                                                                    type="button"
                                                                    className={`avatar-chat-action-btn ${
                                                                        qa.label.length > 22
                                                                            ? 'avatar-chat-action-btn--long'
                                                                            : ''
                                                                    }${
                                                                        isDarkMode &&
                                                                        pressedQuickActionId === qa.id
                                                                            ? ' avatar-chat-action-btn--pressed'
                                                                            : ''
                                                                    }`}
                                                                    onPointerDown={() => {
                                                                        if (!isDarkMode) return;
                                                                        flushSync(() =>
                                                                            setPressedQuickActionId(qa.id)
                                                                        );
                                                                    }}
                                                                    onPointerUp={() => {
                                                                        setPressedQuickActionId(null);
                                                                    }}
                                                                    onPointerLeave={() => {
                                                                        setPressedQuickActionId(null);
                                                                    }}
                                                                    onPointerCancel={() => {
                                                                        setPressedQuickActionId(null);
                                                                    }}
                                                                    onClick={(e) => {
                                                                        handleQuickAction(
                                                                            qa.id,
                                                                            qa.label
                                                                        );
                                                                        setPressedQuickActionId(null);
                                                                        if (isDarkMode) {
                                                                            window.setTimeout(
                                                                                () =>
                                                                                    e.currentTarget.blur(),
                                                                                0
                                                                            );
                                                                        }
                                                                    }}
                                                                >
                                                                    {qa.label}
                                                                </button>
                                                            ))}
                                                        </div>
                                                    ) : null}
                                                </>
                                            ) : (
                                                truncateLongWords(m.text)
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}
                            {typing && (
                                <div className="avatar-chat-msg assistant">
                                    {avatarImgUrl ? (
                                        <AvatarPortrait src={avatarImgUrl} alt={config.avatarName} />
                                    ) : (
                                        <div className="avatar-chat-portrait-spacer" />
                                    )}
                                    <div className="avatar-chat-msg-body">
                                        <div className="avatar-chat-bubble avatar-chat-bubble--typing">
                                            <span className="avatar-chat-typing-dot" />
                                            <span className="avatar-chat-typing-dot" />
                                            <span className="avatar-chat-typing-dot" />
                                        </div>
                                    </div>
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>
                    </div>

                    {/* Täysleveä pohja: reunat kiinni näyttöön, yläkulmat pyöristetyt */}
                    <div className="avatar-chat-input-dock">
                        <form
                            className="avatar-chat-input-bar"
                            onSubmit={e => {
                                e.preventDefault();
                                e.stopPropagation();
                                handleSend();
                            }}
                        >
                            <div className="avatar-chat-input-wrapper">
                                <input
                                    ref={inputRef}
                                    className="avatar-chat-input"
                                    type="text"
                                    value={input}
                                    onChange={e => setInput(e.target.value)}
                                    placeholder={t('avatar.askQuestion')}
                                    aria-label={t('avatar.askQuestion')}
                                    onKeyDownCapture={e => {
                                        e.nativeEvent?.stopImmediatePropagation?.();
                                        e.stopPropagation();
                                    }}
                                    onKeyUpCapture={e => {
                                        e.nativeEvent?.stopImmediatePropagation?.();
                                        e.stopPropagation();
                                    }}
                                />
                            </div>
                            {canSend && !isDarkMode ? (
                                <button
                                    type="submit"
                                    className="avatar-chat-send-btn"
                                    title={t('common.send')}
                                    aria-label={t('avatar.sendMessage')}
                                    onMouseDown={e => {
                                        e.preventDefault();
                                    }}
                                >
                                    <svg
                                        className="avatar-chat-send-icon"
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
                            ) : null}
                        </form>
                        {isDarkMode && canSend ? (
                            <button
                                type="button"
                                className="avatar-chat-dock-send-fab"
                                title={t('common.send')}
                                aria-label={t('avatar.sendMessage')}
                                onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    handleSend();
                                }}
                            >
                                <img
                                    src={avatarChatSendDarkSvg}
                                    alt=""
                                    width={20}
                                    height={20}
                                    draggable={false}
                                    className="avatar-chat-dock-send-fab__icon"
                                />
                            </button>
                        ) : (
                            <MicButton
                                className="avatar-chat-mic-outside"
                                title={t('avatar.voiceInput')}
                                aria-label={t('avatar.voiceInput')}
                                pressed={avatarMicRecording}
                                onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    if (avatarMicRecording) stopAvatarVoiceInput();
                                    else startAvatarVoiceInput();
                                }}
                            />
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

const AvatarChatOverlay: React.FC = () => {
    const ctrl = useControl();
    if (!ctrl.avatarChatOpen || !ctrl.avatarChatConfig) return null;
    return <AvatarChatOverlayInner />;
};

export default AvatarChatOverlay;
