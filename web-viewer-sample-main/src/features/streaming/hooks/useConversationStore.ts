import { useState, useCallback, useRef } from 'react';
import type { AvatarChatMessage } from '../overlays/avatarChat/AvatarChatOverlay';

export interface ConversationStore {
    getMessages: (avatarId: string) => AvatarChatMessage[];
    addMessage: (avatarId: string, msg: AvatarChatMessage) => void;
    hasConversation: (avatarId: string) => boolean;
    clearConversation: (avatarId: string) => void;
}

/**
 * Per-avatar conversation store that persists in React state for the
 * lifetime of the session (until page refresh). Closing the chat overlay
 * does NOT clear messages — users can continue conversations later.
 */
export function useConversationStore(): ConversationStore {
    const [store, setStore] = useState<Record<string, AvatarChatMessage[]>>({});
    const storeRef = useRef(store);
    storeRef.current = store;

    const getMessages = useCallback(
        (avatarId: string): AvatarChatMessage[] => storeRef.current[avatarId] ?? [],
        [],
    );

    const addMessage = useCallback(
        (avatarId: string, msg: AvatarChatMessage) => {
            setStore(prev => ({
                ...prev,
                [avatarId]: [...(prev[avatarId] ?? []), msg],
            }));
        },
        [],
    );

    const hasConversation = useCallback(
        (avatarId: string): boolean => {
            const msgs = storeRef.current[avatarId];
            if (!msgs || msgs.length === 0) return false;
            return msgs.some(m => m.role === 'user');
        },
        [],
    );

    const clearConversation = useCallback(
        (avatarId: string) => {
            setStore(prev => {
                const next = { ...prev };
                delete next[avatarId];
                return next;
            });
        },
        [],
    );

    return { getMessages, addMessage, hasConversation, clearConversation };
}
