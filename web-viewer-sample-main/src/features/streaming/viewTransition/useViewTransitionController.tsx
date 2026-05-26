import { useCallback, useEffect, useRef, useState, type ReactElement } from 'react';
import {
    DEFAULT_VIEW_TRANSITION_MESSAGE,
    VIEW_TRANSITION_FADE_IN_MS,
    VIEW_TRANSITION_FADE_OUT_MS,
} from './constants';
import { subscribeViewTransitionKitReady } from './viewTransitionChannel';
import type { BeginViewTransitionOptions } from './types';
import type { ViewTransitionPhase } from './ViewTransitionOverlay';
import ViewTransitionOverlay from './ViewTransitionOverlay';

export interface UseViewTransitionControllerOptions {
    fadeOutMs?: number;
    fadeInMs?: number;
    defaultMessage?: string;
}

export function useViewTransitionController(
    options?: UseViewTransitionControllerOptions,
): {
    overlay: ReactElement;
    begin: (opts?: BeginViewTransitionOptions) => void;
    phase: ViewTransitionPhase;
} {
    const fadeOutMs = options?.fadeOutMs ?? VIEW_TRANSITION_FADE_OUT_MS;
    const fadeInMs = options?.fadeInMs ?? VIEW_TRANSITION_FADE_IN_MS;
    const defaultMessage = options?.defaultMessage ?? DEFAULT_VIEW_TRANSITION_MESSAGE;

    const [phase, setPhase] = useState<ViewTransitionPhase>('idle');
    const [message, setMessage] = useState(defaultMessage);
    const kitReadyPendingRef = useRef(false);
    const onFadeOutCompleteRef = useRef<(() => void) | null>(null);

    useEffect(() => {
        return subscribeViewTransitionKitReady(() => {
            setPhase((p) => {
                if (p === 'solid') return 'fadeIn';
                if (p === 'fadeOut') {
                    kitReadyPendingRef.current = true;
                }
                return p;
            });
        });
    }, []);

    /** If opacity transitionend is skipped (browser / layer quirks), phase can stay 'fadeIn' forever and block new transitions. */
    useEffect(() => {
        if (phase !== 'fadeIn') return;
        const ms = fadeInMs + 200;
        const id = window.setTimeout(() => {
            setPhase((p) => (p === 'fadeIn' ? 'idle' : p));
        }, ms);
        return () => window.clearTimeout(id);
    }, [phase, fadeInMs]);

    useEffect(() => {
        if (phase !== 'solid') return;
        const cb = onFadeOutCompleteRef.current;
        if (cb) {
            onFadeOutCompleteRef.current = null;
            cb();
        }
        if (!kitReadyPendingRef.current) return;
        kitReadyPendingRef.current = false;
        setPhase('fadeIn');
    }, [phase]);

    const handleOpacityTransitionEnd = useCallback((e: React.TransitionEvent<HTMLDivElement>) => {
        if (e.target !== e.currentTarget) return;
        if (e.propertyName !== 'opacity') return;
        setPhase((p) => {
            if (p === 'fadeOut') return 'solid';
            if (p === 'fadeIn') return 'idle';
            return p;
        });
    }, []);

    const begin = useCallback(
        (opts?: BeginViewTransitionOptions) => {
            setPhase((p) => {
                if (p !== 'idle') return p;
                return 'fadeOut';
            });
            setMessage(opts?.message ?? defaultMessage);
            kitReadyPendingRef.current = false;
            onFadeOutCompleteRef.current = opts?.onFadeOutComplete ?? null;
        },
        [defaultMessage],
    );

    const overlay: ReactElement = (
        <ViewTransitionOverlay
            phase={phase}
            message={message}
            fadeOutMs={fadeOutMs}
            fadeInMs={fadeInMs}
            onOpacityTransitionEnd={handleOpacityTransitionEnd}
        />
    );

    return { overlay, begin, phase };
}
