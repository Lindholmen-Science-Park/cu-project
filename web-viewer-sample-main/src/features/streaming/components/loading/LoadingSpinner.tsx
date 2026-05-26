import React from 'react';
import spinner from '@icons/loading/spinner.gif';

interface LoadingSpinnerProps {
    size?: number;
    label?: string;
}

/**
 * Single brand spinner (white circle + dark "G" icon) used by every loading
 * screen. Marked with `essential-motion` so it keeps animating under
 * `prefers-reduced-motion` (load progress is an essential indicator —
 * WCAG 2.2.2 accepted exception).
 */
const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
    size = 180,
    label,
}) => {
    return (
        <img
            src={spinner}
            alt=""
            role="progressbar"
            aria-label={label}
            aria-valuetext={label}
            className="loading-spinner essential-motion"
            style={{ width: size, height: size }}
            draggable={false}
        />
    );
};

export default LoadingSpinner;
