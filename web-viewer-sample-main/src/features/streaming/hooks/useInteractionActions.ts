import { useRef, useCallback } from 'react';

export type InteractionActionHandler = (interactableId: string, payload: any) => void;

/**
 * Pluggable action dispatch registry for interaction click events.
 *
 * Modules register handlers by action name (e.g. "avatarChat.open", "door.open").
 * The custom event handler calls `dispatch()` instead of growing if-else chains.
 */
export function useInteractionActions() {
    const handlersRef = useRef<Map<string, InteractionActionHandler>>(new Map());

    const register = useCallback((action: string, handler: InteractionActionHandler) => {
        handlersRef.current.set(action, handler);
    }, []);

    const unregister = useCallback((action: string) => {
        handlersRef.current.delete(action);
    }, []);

    const dispatch = useCallback((interactableId: string, action: string, payload: any): boolean => {
        const handler = handlersRef.current.get(action);
        if (handler) {
            handler(interactableId, payload);
            return true;
        }
        return false;
    }, []);

    return { register, unregister, dispatch };
}
