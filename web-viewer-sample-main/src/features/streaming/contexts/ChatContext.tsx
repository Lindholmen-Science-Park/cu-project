import React, { createContext, useContext, useState, useCallback, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { sendMessage } from '../messaging';
import { aiLanguageFor } from '../../../services/aiLanguage';
import { parseVoiceProfile, FEMALE_VOICE_PROFILE } from '../../../services/speechSynthesis';
import { useConversationStore } from '../hooks/useConversationStore';
import { useInteractionActions } from '../hooks/useInteractionActions';
import type { AvatarChatConfig, AvatarChatMessage } from '../overlays/avatarChat/AvatarChatOverlay';
import { useControl } from './ControlContext';
import { useStream } from './StreamContext';
import { useSpatialSound } from './SpatialSoundContext';
import { useVideo360 } from './Video360Context';

// NOTE: avatar identity (id, name, image, primPath, chatBackgroundImage,
// voiceProfile) lives in Kit's `interactions.json` (`avatar_red.npcConfig`).
// We mirror just enough here to drive the search-bar "welcome" entry point,
// which has no real interaction click — without this mirror the search-bar
// chat would have no avatar config to attach to.
//
// Voice is mirrored alongside the rest because the search-bar entry path
// never receives a Kit `avatarChat.open` payload, so without a frontend
// default the chat falls through to NEUTRAL_VOICE_PROFILE → the OS default
// voice, which on most machines is male (mismatching Red's character).
// Whenever Kit *does* send an `avatarChat.open` payload (NPC click path),
// the parsed payload voice still overrides this default — see line ~88 —
// so Kit remains the source of truth for runtime voice changes.
//
// TODO(multi-avatar): when a second chat-capable NPC is added, drop this
// constant entirely. Have Kit pick one NPC as the "search assistant" (e.g.
// via an `isSearchAssistant: true` flag in interactions.json) and ship its
// full config to the frontend at scene-ready time, so all avatar identity
// (name, image, voice, …) is data-driven from Kit instead of hardcoded.
const WELCOME_AVATAR_CHAT_BASE = {
    avatarId: 'red' as const,
    avatarName: 'Red',
    avatarImage: 'red_image.png',
    primPath: '/World/Red',
    chatBackgroundImage: 'red.svg',
    voiceProfile: FEMALE_VOICE_PROFILE,
};

export interface ChatContextType {
    conversation: ReturnType<typeof useConversationStore>;
    interactionActions: ReturnType<typeof useInteractionActions>;
    chatOpenSource: 'npc' | 'search' | null;
    setChatOpenSource: React.Dispatch<React.SetStateAction<'npc' | 'search' | null>>;
    avatarAgentTyping: boolean;
    welcomeAvatarChatConfig: AvatarChatConfig;
    lastAIResponseText?: string;
    lastAIResponseIsError?: boolean;
    handleChatClose: () => void;
    handleChatBack: (() => void) | undefined;
    handleChatSend: (text: string) => void;
    handleChatQuickAction: (actionId: string) => void;
    handleChatUserMessage: (msg: AvatarChatMessage) => void;
    handleSearchSendToAI: (text: string) => void;
    handleOpenAssistantChat: () => void;
    setAvatarAgentTyping: React.Dispatch<React.SetStateAction<boolean>>;
}

const ChatContext = createContext<ChatContextType | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
    const { t, i18n } = useTranslation();
    const ctrl = useControl();
    const stream = useStream();
    const spatialSound = useSpatialSound();
    const video360 = useVideo360();

    const welcomeAvatarChatConfig = useMemo<AvatarChatConfig>(() => ({
        ...WELCOME_AVATAR_CHAT_BASE,
        greeting: t('interactions.avatar_red.greeting'),
        quickActions: [
            { id: 'navigate_help', label: t('interactions.avatar_red.quickAction_navigate_help') },
            { id: 'horseshow_info', label: t('interactions.avatar_red.quickAction_horseshow_info') },
        ],
    }), [t]);

    const interactionActions = useInteractionActions();
    const conversation = useConversationStore();

    const [avatarAgentTyping, setAvatarAgentTyping] = useState(false);
    const [chatOpenSource, setChatOpenSource] = useState<'npc' | 'search' | null>(null);
    const [sentFromSearchView, setSentFromSearchView] = useState(false);

    // Register avatarChat.open interaction
    useEffect(() => {
        interactionActions.register('avatarChat.open', (_interactableId: string, payload: any) => {
            const avatarId = String(payload.avatarId || '');

            // Voice character lives in `interactions.json` (avatar's
            // `npcConfig.voice`). `undefined` means "no preference" → the
            // shared TTS layer falls back to NEUTRAL_VOICE_PROFILE. The
            // frontend deliberately doesn't pick a default so Kit stays
            // the single source of truth for per-avatar voice data.
            const voiceProfile = parseVoiceProfile(payload.voice ?? payload.voiceProfile);

            if (avatarId === WELCOME_AVATAR_CHAT_BASE.avatarId) {
                // Red uses the i18n-resolved welcome config (Kit ships i18n
                // keys for greeting / quickActions), but voice still comes
                // from the Kit payload so it doesn't get re-duplicated here.
                ctrl.setAvatarChatConfig({ ...welcomeAvatarChatConfig, voiceProfile });
                ctrl.setAvatarChatOpen(true);
                setChatOpenSource('npc');
                return;
            }

            const name = String(payload.avatarName || t('streaming.defaultAvatarName'));
            const config: AvatarChatConfig = {
                avatarId,
                avatarName: name,
                avatarImage: payload.avatarImage,
                greeting: String(payload.greeting || t('streaming.defaultGreeting')),
                quickActions: Array.isArray(payload.quickActions) ? payload.quickActions : [],
                primPath: payload.primPath || `/World/${name}`,
                chatBackgroundImage: payload.chatBackgroundImage,
                voiceProfile,
            };
            ctrl.setAvatarChatConfig(config);
            ctrl.setAvatarChatOpen(true);
            setChatOpenSource('npc');
        });
        return () => { interactionActions.unregister('avatarChat.open'); };
    }, [interactionActions, ctrl.setAvatarChatConfig, ctrl.setAvatarChatOpen, welcomeAvatarChatConfig, t]);

    // Register videobook.open interaction (3D ipad / interactable — same splash + 4s → autoplay as icon bubble)
    useEffect(() => {
        interactionActions.register('videobook.open', (_interactableId: string, payload: any) => {
            if (!payload || !payload.iconId) return;
            ctrl.setVideobookShowEntrySplash(true);
            ctrl.setVideobookEntry({
                id: String(payload.iconId),
                iconId: String(payload.iconId),
                title: String(payload.title || ''),
                subtitle: String(payload.subtitle || ''),
                videoUrl: String(payload.videoUrl || ''),
                captionsUrl: payload.captionsUrl ? String(payload.captionsUrl) : undefined,
                chapters: Array.isArray(payload.chapters) ? payload.chapters : [],
            });
            ctrl.setVideobookOpen(true);
        });
        return () => { interactionActions.unregister('videobook.open'); };
    }, [interactionActions, ctrl.setVideobookEntry, ctrl.setVideobookOpen, ctrl.setVideobookShowEntrySplash]);

    // Register spatialSound.open interaction
    useEffect(() => {
        interactionActions.register('spatialSound.open', (_interactableId: string, payload: any) => {
            if (!payload || !payload.iconId) return;
            const primName = String(payload.iconName || payload.iconId || '');
            spatialSound.open({
                id: String(payload.iconId),
                iconId: String(payload.iconId),
                title: String(payload.title || ''),
                soundUrl: String(payload.soundUrl || ''),
                soundTitle: String(payload.soundTitle || ''),
                captionsUrl: payload.captionsUrl ? String(payload.captionsUrl) : undefined,
                primPath: payload.primPath || (primName ? `/World/${primName}` : undefined),
            });
        });
        return () => { interactionActions.unregister('spatialSound.open'); };
    }, [interactionActions, spatialSound.open]);

    // Register coinPoi.open interaction — POI coins (round signs) clicked
    // in 3D. Payload carries the linked POI's metadata so the info card can
    // render fee / accessibility / cleaning / seats without an extra Kit
    // round-trip. See `.cursor/rules/topics/poi-coins.mdc`.
    useEffect(() => {
        interactionActions.register('coinPoi.open', (_interactableId: string, payload: any) => {
            if (!payload) return;
            ctrl.setCoinPoiPayload({
                poiType: String(payload.poiType || ''),
                xformId: String(payload.xformId || ''),
                coinType: String(payload.coinType || ''),
                primPath: payload.primPath ? String(payload.primPath) : undefined,
                displayName: payload.displayName ? String(payload.displayName) : undefined,
                labelIcon: payload.labelIcon ? String(payload.labelIcon) : undefined,
                metadata: (payload.metadata && typeof payload.metadata === 'object')
                    ? payload.metadata as Record<string, unknown>
                    : {},
            });
            ctrl.setCoinPoiOpen(true);
        });
        return () => { interactionActions.unregister('coinPoi.open'); };
    }, [interactionActions, ctrl.setCoinPoiPayload, ctrl.setCoinPoiOpen]);

    // Register video360.open interaction (3D click on a video_360_* Xform)
    useEffect(() => {
        interactionActions.register('video360.open', (_interactableId: string, payload: any) => {
            if (!payload || !payload.iconId) return;
            const primName = String(payload.iconName || payload.iconId || '');
            video360.open({
                id: String(payload.iconId),
                iconId: String(payload.iconId),
                title: String(payload.title || ''),
                videoUrl: String(payload.videoUrl || ''),
                videoTitle: String(payload.videoTitle || ''),
                captionsUrl: payload.captionsUrl ? String(payload.captionsUrl) : undefined,
                primPath: payload.primPath || (primName ? `/World/${primName}` : undefined),
            });
        });
        return () => { interactionActions.unregister('video360.open'); };
    }, [interactionActions, video360.open]);

    // Request video catalog from Kit on scene ready
    useEffect(() => {
        if (!stream.streamReady || stream.sceneLoading) return;
        sendMessage('videoListRequest', {});
    }, [stream.streamReady, stream.sceneLoading]);

    useEffect(() => {
        interactionActions.register('video.open', (_interactableId: string, payload: any) => {
            ctrl.handlePlayVideo({
                id: String(payload.videoId || payload.id || ''),
                title: String(payload.title || t('streaming.defaultVideoTitle')),
                description: payload.description ? String(payload.description) : undefined,
                source: String(payload.source || ''),
                durationSeconds: payload.durationSeconds ? Number(payload.durationSeconds) : undefined,
                onCompleteAction: payload.onCompleteAction || undefined,
            });
        });
        return () => { interactionActions.unregister('video.open'); };
    }, [interactionActions, ctrl.handlePlayVideo, t]);

    // Hide/show avatar prim when chat opens/closes
    useEffect(() => {
        if (!stream.streamReady || chatOpenSource !== 'npc') return;
        const primPath = ctrl.avatarChatConfig?.primPath;
        if (!primPath || !ctrl.avatarChatOpen) return;
        sendMessage('avatarPrim.hide', { primPath });
        return () => {
            sendMessage('avatarPrim.show', { primPath });
        };
    }, [ctrl.avatarChatOpen, chatOpenSource, ctrl.avatarChatConfig?.primPath, stream.streamReady]);

    useEffect(() => {
        if (!stream.streamReady || !ctrl.avatarChatOpen) return;
        sendMessage('npcMarkers.hide', {});
        return () => { sendMessage('npcMarkers.show', {}); };
    }, [ctrl.avatarChatOpen, stream.streamReady]);

    // Hide/show icon prim and markers when spatial sound player opens/closes
    useEffect(() => {
        if (!stream.streamReady || !spatialSound.isOpen) return;
        const primPath = spatialSound.entry?.primPath;
        if (!primPath) return;
        sendMessage('avatarPrim.hide', { primPath });
        sendMessage('npcMarkers.hide', {});
        return () => {
            sendMessage('avatarPrim.show', { primPath });
            sendMessage('npcMarkers.show', {});
        };
    }, [spatialSound.isOpen, spatialSound.entry?.primPath, stream.streamReady]);

    // AI response tracking for search view
    const welcomeMessages = conversation.getMessages(welcomeAvatarChatConfig.avatarId);
    const lastAIResponse = useMemo(() => {
        if (!sentFromSearchView) return undefined;
        for (let i = welcomeMessages.length - 1; i >= 0; i--) {
            if (welcomeMessages[i].role === 'assistant') return welcomeMessages[i];
        }
        return undefined;
    }, [welcomeMessages, sentFromSearchView]);

    // Chat handlers
    const handleChatClose = useCallback(() => {
        ctrl.setAvatarChatOpen(false);
        setChatOpenSource(null);
    }, [ctrl.setAvatarChatOpen]);

    const handleChatBack = useMemo(
        () => chatOpenSource === 'search' ? handleChatClose : undefined,
        [chatOpenSource, handleChatClose],
    );

    const handleChatSend = useCallback((text: string) => {
        sendMessage('ai.agent.request', {
            text,
            avatarId: ctrl.avatarChatConfig!.avatarId,
            language: aiLanguageFor(i18n.language),
        });
    }, [ctrl.avatarChatConfig, i18n.language]);

    const handleChatQuickAction = useCallback((actionId: string) => {
        const action = ctrl.avatarChatConfig!.quickActions?.find(a => a.id === actionId);
        sendMessage('ai.agent.request', {
            text: action?.label ?? actionId,
            avatarId: ctrl.avatarChatConfig!.avatarId,
            quickActionId: actionId,
            language: aiLanguageFor(i18n.language),
        });
    }, [ctrl.avatarChatConfig, i18n.language]);

    const handleChatUserMessage = useCallback((msg: AvatarChatMessage) => {
        conversation.addMessage(ctrl.avatarChatConfig!.avatarId, msg);
    }, [conversation, ctrl.avatarChatConfig]);

    const handleSearchSendToAI = useCallback((text: string) => {
        const avatarId = welcomeAvatarChatConfig.avatarId;
        conversation.addMessage(avatarId, { role: 'user', text });
        setSentFromSearchView(true);
        sendMessage('ai.agent.request', {
            text,
            avatarId,
            language: aiLanguageFor(i18n.language),
        });
    }, [conversation, welcomeAvatarChatConfig.avatarId, i18n.language]);

    const handleOpenAssistantChat = useCallback(() => {
        ctrl.setAvatarChatConfig(welcomeAvatarChatConfig);
        ctrl.setAvatarChatOpen(true);
        setChatOpenSource('search');
        setSentFromSearchView(false);
    }, [ctrl.setAvatarChatConfig, ctrl.setAvatarChatOpen, welcomeAvatarChatConfig]);

    const value = useMemo<ChatContextType>(() => ({
        conversation,
        interactionActions,
        chatOpenSource,
        setChatOpenSource,
        avatarAgentTyping,
        welcomeAvatarChatConfig,
        lastAIResponseText: lastAIResponse?.text,
        lastAIResponseIsError: lastAIResponse?.isError,
        handleChatClose,
        handleChatBack,
        handleChatSend,
        handleChatQuickAction,
        handleChatUserMessage,
        handleSearchSendToAI,
        handleOpenAssistantChat,
        setAvatarAgentTyping,
    }), [
        conversation, interactionActions, chatOpenSource, avatarAgentTyping,
        welcomeAvatarChatConfig, lastAIResponse,
        handleChatClose, handleChatBack, handleChatSend, handleChatQuickAction,
        handleChatUserMessage, handleSearchSendToAI, handleOpenAssistantChat,
    ]);

    return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatContextType {
    const ctx = useContext(ChatContext);
    if (!ctx) throw new Error('useChat must be used within ChatProvider');
    return ctx;
}

export { ChatContext };
