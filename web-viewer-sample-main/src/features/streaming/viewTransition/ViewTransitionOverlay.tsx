import React from 'react';
import { LoadingScreen } from '../components/loading';
import './ViewTransitionOverlay.css';

export type ViewTransitionPhase = 'idle' | 'fadeOut' | 'solid' | 'fadeIn';

export interface ViewTransitionOverlayProps {
    phase: ViewTransitionPhase;
    message: string;
    fadeOutMs: number;
    fadeInMs: number;
    onOpacityTransitionEnd: (e: React.TransitionEvent<HTMLDivElement>) => void;
}

/**
 * Full-screen brand canvas with timed opacity transitions for camera / spawn
 * flows. Driven by {@link useViewTransitionController}: idle → fadeOut →
 * solid (Kit work happens here) → fadeIn → idle. Renders the same brand
 * loading visual (purple + arcs + spinner + label + EU footer) as the boot
 * and scene-loading screens.
 */
const ViewTransitionOverlay: React.FC<ViewTransitionOverlayProps> = ({
    phase,
    message,
    fadeOutMs,
    fadeInMs,
    onOpacityTransitionEnd,
}) => {
    const style = {
        '--vt-fade-out': `${fadeOutMs}ms`,
        '--vt-fade-in': `${fadeInMs}ms`,
    } as React.CSSProperties;

    return (
        <div
            className={`view-transition-layer view-transition-layer--${phase}`}
            style={style}
            aria-hidden={phase === 'idle'}
            onTransitionEnd={onOpacityTransitionEnd}
        >
            {/* Reuse the brand loading visual; the wrapper handles opacity transitions. */}
            <LoadingScreen
                message={message}
                visible
                blocking={false}
                fadeMs={0}
            />
        </div>
    );
};

export default ViewTransitionOverlay;
