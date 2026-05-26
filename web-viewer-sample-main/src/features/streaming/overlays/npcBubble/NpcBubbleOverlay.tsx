import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppUI, useChat, useControl, useStream } from '../../contexts';
import './NpcBubbleOverlay.css';
import imageAvatarSvg from '@icons/interaction/image-avatar.svg';
import type { NearestNpcInfo } from '../../hooks/useControlHandlers';
import { speakText, type SpeechController } from '../../../../services/speechSynthesis';
import TtsSpeakerIcon from '../TtsSpeakerIcon';

const NpcBubbleOverlayInner: React.FC<{ npc: NearestNpcInfo }> = ({ npc }) => {
    const { t, i18n } = useTranslation();
    const appUI = useAppUI();
    const chat = useChat();
    const [ttsPlaying, setTtsPlaying] = useState(false);
    const ttsControllerRef = useRef<SpeechController | null>(null);

    const cfg = npc.npcConfig;

    const greeting = t(cfg.greeting || '');

    // Cancel any in-flight utterance on unmount.
    useEffect(() => {
        return () => {
            ttsControllerRef.current?.cancel();
        };
    }, []);

    const handleSpeak = useCallback((e: React.MouseEvent) => {
        e.stopPropagation();
        if (ttsPlaying) {
            ttsControllerRef.current?.cancel();
            setTtsPlaying(false);
            return;
        }
        ttsControllerRef.current = speakText(greeting, {
            uiLang: i18n.language,
            voiceProfile: cfg.voiceProfile,
            onStart: () => setTtsPlaying(true),
            onEnd: () => setTtsPlaying(false),
            onError: () => setTtsPlaying(false),
        });
    }, [greeting, ttsPlaying, i18n.language, cfg.voiceProfile]);

    const handleClick = useCallback(() => {
        chat.interactionActions.dispatch('overlay', 'avatarChat.open', cfg as Record<string, any>);
    }, [chat.interactionActions, cfg]);

    return (
        <div className={`npc-bubble-wrap${appUI.streamNavOverlayActive ? ' npc-bubble-wrap--automove' : ''}`}>
            <span className="npc-bubble-avatar-wrap" aria-hidden>
                <img src={imageAvatarSvg} alt="" draggable={false} />
            </span>
            <div className="npc-bubble-body">
                <button
                    type="button"
                    tabIndex={appUI.streamNavOverlayActive ? -1 : 0}
                    className="npc-bubble-open"
                    aria-label={t('avatar.openChatWithGuide')}
                    onClick={handleClick}
                >
                    <span className="npc-bubble-text">{greeting}</span>
                </button>
                <button
                    type="button"
                    tabIndex={appUI.streamNavOverlayActive ? -1 : 0}
                    className={`npc-bubble-speaker${ttsPlaying ? ' npc-bubble-speaker--playing' : ''}`}
                    title={ttsPlaying ? t('common.stopListening') : t('common.listen')}
                    aria-label={ttsPlaying ? t('common.stopListening') : t('common.listen')}
                    aria-pressed={ttsPlaying}
                    onClick={handleSpeak}
                >
                    <TtsSpeakerIcon className="npc-bubble-speaker-icon" />
                </button>
            </div>
        </div>
    );
};

const NpcBubbleOverlay: React.FC = () => {
    const ctrl = useControl();
    const stream = useStream();
    if (ctrl.avatarChatOpen || stream.sceneLoading || !ctrl.nearestNpc) return null;
    return <NpcBubbleOverlayInner npc={ctrl.nearestNpc} />;
};

export default NpcBubbleOverlay;
