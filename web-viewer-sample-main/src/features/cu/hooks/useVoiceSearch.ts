import { useRef, useCallback, useEffect, useState } from 'react';

type RecInstance = {
    lang: string;
    interimResults: boolean;
    maxAlternatives: number;
    onresult: ((ev: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null;
    onerror: (() => void) | null;
    onend: (() => void) | null;
    start: () => void;
    stop: () => void;
};

type RecCtor = new () => RecInstance;

/**
 * Manages Web Speech API voice recognition.
 * Returns start/stop/cleanup — caller provides onTextUpdate to receive transcribed text.
 */
export function useVoiceSearch(onTextUpdate: (text: string) => void) {
    const recognitionRef = useRef<{ stop: () => void } | null>(null);
    const onTextUpdateRef = useRef(onTextUpdate);
    onTextUpdateRef.current = onTextUpdate;
    const [isListening, setIsListening] = useState(false);

    const stop = useCallback(() => {
        try {
            recognitionRef.current?.stop();
        } catch {
            /* ignore */
        }
        setIsListening(false);
    }, []);

    const cleanup = useCallback(() => {
        stop();
        recognitionRef.current = null;
    }, [stop]);

    const start = useCallback(() => {
        if (typeof window === 'undefined') return;

        const w = window as typeof window & {
            SpeechRecognition?: RecCtor;
            webkitSpeechRecognition?: RecCtor;
        };
        const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
        if (!Ctor) return;

        try {
            recognitionRef.current?.stop();
        } catch {
            /* ignore */
        }

        try {
            const rec = new Ctor();
            rec.lang = /^fi/i.test(navigator.language || '') ? 'fi-FI' : 'en-US';
            rec.interimResults = true;
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
                if (normalized) onTextUpdateRef.current(normalized);
            };
            rec.onerror = () => {
                recognitionRef.current = null;
                setIsListening(false);
            };
            rec.onend = () => {
                recognitionRef.current = null;
                setIsListening(false);
            };
            recognitionRef.current = rec;
            rec.start();
            setIsListening(true);
        } catch {
            recognitionRef.current = null;
            setIsListening(false);
        }
    }, []);

    /**
     * Toggle for keyboard / single-tap users. Works as a click-to-toggle
     * companion to the existing push-to-talk pointerdown/pointerup flow,
     * so keyboard users can activate the mic with Enter / Space.
     */
    const toggle = useCallback(() => {
        if (recognitionRef.current) {
            stop();
        } else {
            start();
        }
    }, [start, stop]);

    useEffect(() => () => cleanup(), [cleanup]);

    return { start, stop, toggle, cleanup, isListening };
}
