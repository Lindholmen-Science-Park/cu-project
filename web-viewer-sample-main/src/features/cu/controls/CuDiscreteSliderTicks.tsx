import React from 'react';
import './CuDiscreteSliderTicks.css';

export interface CuDiscreteSliderTicksProps {
    /** Pre-translated tick strings (order matches slider stops left → right). */
    labels: string[];
    className?: string;
    /** Native thumb width in px — must match ::-webkit-slider-thumb width for alignment. */
    thumbWidthPx?: number;
}

/**
 * Tick labels aligned to native range thumb centers (linear spacing over the slider width).
 * Parent width should match the range input width (e.g. same column as the track).
 */
const CuDiscreteSliderTicks: React.FC<CuDiscreteSliderTicksProps> = ({
    labels,
    className,
    thumbWidthPx = 24,
}) => {
    const n = labels.length;
    if (n === 0) return null;

    const half = thumbWidthPx / 2;

    if (n === 1) {
        return (
            <div
                className={`cu-discrete-slider-ticks cu-discrete-slider-ticks--single ${className ?? ''}`.trim()}
                aria-hidden={true}
            >
                <span className="cu-discrete-slider-ticks__tick">{labels[0]}</span>
            </div>
        );
    }

    return (
        <div
            className={`cu-discrete-slider-ticks ${className ?? ''}`.trim()}
            style={
                {
                    '--cu-thumb-half': `${half}px`,
                    '--cu-tick-count': n,
                } as React.CSSProperties
            }
            aria-hidden={true}
        >
            {labels.map((text, i) => (
                <span
                    key={`${i}-${text}`}
                    className="cu-discrete-slider-ticks__tick"
                    style={{ ['--cu-tick-index' as string]: i }}
                >
                    {text}
                </span>
            ))}
        </div>
    );
};

export default CuDiscreteSliderTicks;
