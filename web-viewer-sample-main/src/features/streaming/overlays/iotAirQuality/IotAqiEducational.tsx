import React, { useId, useMemo } from 'react';
import './IotAqiEducational.css';

const AQI_MAX = 500;
const TICK_VALUES = [0, 50, 100, 150, 200, 300, 500] as const;
const SCALE_HINT = 'US AQI 0–500 scale. Lower is better.';

function normalizeAqi(raw: unknown): number {
    if (typeof raw === 'number' && Number.isFinite(raw) && raw >= 0) return raw;
    if (typeof raw === 'string') {
        const n = parseInt(raw.trim(), 10);
        if (Number.isFinite(n) && n >= 0) return n;
    }
    return -1;
}

/** Dev-only: US AQI scale + marker (English, not in customer i18n). */
const IotAqiEducational: React.FC<{ aqi: unknown }> = ({ aqi }) => {
    const scaleDescId = useId();
    const value = useMemo(() => normalizeAqi(aqi), [aqi]);
    const has = value >= 0;
    const pct = has ? Math.min(100, (Math.min(AQI_MAX, value) / AQI_MAX) * 100) : 0;

    return (
        <div className="iot-aqi-edu">
            <p id={scaleDescId} className="iot-aqi-edu-short">
                {SCALE_HINT}
            </p>
            <div className="iot-aqi-scale-block" role="img" aria-labelledby={scaleDescId}>
                <div className="iot-aqi-scale" aria-hidden>
                    <div className="iot-aqi-scale-track" />
                    {has ? (
                        <div
                            className="iot-aqi-scale-marker"
                            style={{ left: `${pct}%` }}
                            title={String(Math.round(value))}
                        />
                    ) : null}
                </div>
                <div className="iot-aqi-scale-labels" aria-hidden>
                    {TICK_VALUES.map((v) => (
                        <span key={v} className="iot-aqi-scale-tick" style={{ left: `${(v / AQI_MAX) * 100}%` }}>
                            {v}
                        </span>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default IotAqiEducational;
