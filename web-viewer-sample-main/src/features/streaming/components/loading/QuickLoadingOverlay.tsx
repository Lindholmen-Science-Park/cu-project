import React from 'react';
import LoadingSpinner from './LoadingSpinner';
import LoadingFooter from './LoadingFooter';
import './QuickLoadingOverlay.css';

export interface QuickLoadingOverlayProps {
    /** Centered label rendered under the spinner. Optional. */
    message?: string;
    /** When true, the overlay can be dismissed by clicking through (no scrim). */
    nonBlocking?: boolean;
    /**
     * `fullscreen` — fixed overlay over the viewport (default).
     * `embedded` — `position: absolute` fill; parent must be `position: relative` (or other positioning).
     */
    layout?: 'fullscreen' | 'embedded';
    /** Passed to `LoadingSpinner` (default 180). */
    spinnerSize?: number;
}

/**
 * Translucent in-context loading indicator — Navy Purple scrim at 60% opacity,
 * centered brand spinner + optional label, and the same EU funding footer as
 * `LoadingScreen` (Citiverses + EU co-funded lockup + disclaimer). Fullscreen
 * layout keeps the 60% Navy Purple scrim over the stream; `layout="embedded"`
 * uses a lighter veil + blur so in-panel loaders do not read as a solid gray slab.

 *
 * Use `layout="embedded"` inside a positioned panel (e.g. `position: relative`
 * scroll region) so the scrim covers only that region instead of the full viewport.
 */
const QuickLoadingOverlay: React.FC<QuickLoadingOverlayProps> = ({
    message,
    nonBlocking = false,
    layout = 'fullscreen',
    spinnerSize = 180,
}) => {
    const cls =
        layout === 'embedded'
            ? 'quick-loading-overlay quick-loading-overlay--embedded'
            : 'quick-loading-overlay';
    return (
        <div
            className={cls}
            role="status"
            aria-live="polite"
            aria-busy="true"
            style={nonBlocking ? { pointerEvents: 'none' } : undefined}
        >
            <div className="quick-loading-overlay__main">
                <LoadingSpinner size={spinnerSize} label={message} />
                {message && <div className="quick-loading-overlay__label">{message}</div>}
            </div>
            <LoadingFooter />
        </div>
    );
};

export default QuickLoadingOverlay;
