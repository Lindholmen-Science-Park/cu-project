import React from 'react';
import LoadingSpinner from './LoadingSpinner';
import LoadingFooter from './LoadingFooter';
import decorativeArcs from '@icons/loading/decorativeArcs.svg';
import './LoadingScreen.css';

export interface LoadingScreenProps {
    /** Centered label (e.g. "Loading Overview…"). */
    message?: string;
    /** Optional CTA below the label (Retry, Re-request status, etc.). */
    actionLabel?: string;
    onAction?: () => void;
    /** Internal: lifts opacity to 1 once mounted (for fade-in transitions). */
    visible?: boolean;
    /** Fade transition duration in ms — used by view-transition timings. */
    fadeMs?: number;
    /** When true, disables interaction; default true while visible. */
    blocking?: boolean;
    /** Optional id for aria-labelledby relationships. */
    titleId?: string;
}

/**
 * Full-viewport brand loading screen — Dark Purple background with the lemon
 * decorative arcs, a centered animated spinner, an optional message, and the
 * EU credits/disclaimer footer. Used for app boot, scene loading, and as the
 * "solid" frame between view-transition fade-out and fade-in.
 */
const LoadingScreen: React.FC<LoadingScreenProps> = ({
    message,
    actionLabel,
    onAction,
    visible = true,
    fadeMs = 250,
    blocking = true,
    titleId,
}) => {
    const style: React.CSSProperties = {
        opacity: visible ? 1 : 0,
        transition: `opacity ${fadeMs}ms ease`,
        pointerEvents: blocking && visible ? 'auto' : 'none',
    };

    return (
        <div
            className="loading-screen"
            style={style}
            role="status"
            aria-live="polite"
            aria-busy={visible}
            aria-labelledby={titleId}
        >
            <img
                src={decorativeArcs}
                alt=""
                aria-hidden="true"
                className="loading-screen__arcs"
                draggable={false}
            />
            <div className="loading-screen__center">
                <LoadingSpinner size={180} label={message} />
                {message && (
                    <div id={titleId} className="loading-screen__label">
                        {message}
                    </div>
                )}
                {actionLabel && onAction && (
                    <button
                        type="button"
                        className="loading-screen__action"
                        onClick={onAction}
                    >
                        {actionLabel}
                    </button>
                )}
            </div>
            <LoadingFooter />
        </div>
    );
};

export default LoadingScreen;
