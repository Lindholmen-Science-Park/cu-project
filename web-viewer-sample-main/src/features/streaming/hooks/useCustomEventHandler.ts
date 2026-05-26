import { useCallback, useRef } from 'react';
import { shouldLogEvent } from '../messaging';
import {
    handleNavigationEvents,
    handleSeatEvents,
    handleCameraEvents,
    handleInteractionEvents,
    handleUsdEditEvents,
    handleSceneEvents,
    handleVideoEvents,
    handleWorldStateEvents,
} from './eventHandlers';
import type { EventStateSetters } from './eventHandlers';

export type { EventStateSetters };

export function useCustomEventHandler(setters: EventStateSetters) {
    const settersRef = useRef(setters);
    settersRef.current = setters;

    const customEventHandlersRef = useRef<Array<(event: any) => void>>([]);

    const clearHandlers = useCallback(() => {
        customEventHandlersRef.current = [];
    }, []);

    const handleCustomEvent = useCallback((event: any) => {
        if (shouldLogEvent(event)) {
            console.log('Custom Event:', event);
        }

        const s = settersRef.current;
        handleSceneEvents(event, s);
        handleNavigationEvents(event, s);
        handleSeatEvents(event, s);
        handleCameraEvents(event, s);
        handleInteractionEvents(event, s);
        handleUsdEditEvents(event, s);
        handleVideoEvents(event, s);
        handleWorldStateEvents(event, s);
    }, []);

    /** Register a child event handler (e.g. ChatWidget). Deduped by identity. */
    const registerChildHandler = useCallback((handler: (event: any) => void) => {
        const arr = customEventHandlersRef.current;
        if (!arr.includes(handler)) arr.push(handler);
    }, []);

    /** Combined dispatcher: own handler + scene events + all registered child handlers. */
    const createCombinedHandler = useCallback(
        (processSceneEvent: (event: any) => boolean) => {
            return (eventOrHandler: any) => {
                if (typeof eventOrHandler === 'function') {
                    registerChildHandler(eventOrHandler);
                    return;
                }
                handleCustomEvent(eventOrHandler);
                processSceneEvent(eventOrHandler);
                for (const handler of customEventHandlersRef.current) {
                    try { handler(eventOrHandler); } catch (e) { console.warn('[StreamOnlyWindow] custom event handler error:', e); }
                }
            };
        },
        [handleCustomEvent, registerChildHandler],
    );

    return {
        customEventHandlersRef,
        clearHandlers,
        handleCustomEvent,
        registerChildHandler,
        createCombinedHandler,
    };
}
