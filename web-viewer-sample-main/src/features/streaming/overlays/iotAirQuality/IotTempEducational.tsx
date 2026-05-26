import React, { useId, useMemo } from 'react';
import './IotAqiEducational.css';

/** Display range for outdoor °C (WAQI); covers Swedish extremes; values clamp to ends for marker position. */
const TEMP_MIN = -50;
const TEMP_MAX = 50;
const TICK_VALUES = [-50, -25, 0, 25, 50] as const;
const SCALE_HINT =
    'Outdoor air temperature (°C) from WAQI when reported. Scale −50 … +50 °C (marker clamps at ends if outside).';

function normalizeTempC(raw: unknown): number {
    if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
    if (typeof raw === 'string') {
        const n = parseFloat(raw.trim());
        if (Number.isFinite(n)) return n;
    }
    return NaN;
}

/** Dev-only: temperature scale + marker (English, not in customer i18n). */
const IotTempEducational: React.FC<{ tempC: unknown }> = ({ tempC }) => {
    const scaleDescId = useId();
    const value = useMemo(() => normalizeTempC(tempC), [tempC]);
    const has = Number.isFinite(value);
    const span = TEMP_MAX - TEMP_MIN;
    const pct = has
        ? Math.min(100, Math.max(0, ((value - TEMP_MIN) / span) * 100))
        : 0;

    return (
        <div className="iot-aqi-edu">
            <p id={scaleDescId} className="iot-aqi-edu-short">
                {SCALE_HINT}
            </p>
            <div className="iot-aqi-scale-block" role="img" aria-labelledby={scaleDescId}>
                <div className="iot-aqi-scale" aria-hidden>
                    <div className="iot-aqi-scale-track iot-temp-scale-track" />
                    {has ? (
                        <div
                            className="iot-aqi-scale-marker"
                            style={{ left: `${pct}%` }}
                            title={`${value.toFixed(1)} °C`}
                        />
                    ) : null}
                </div>
                <div className="iot-aqi-scale-labels" aria-hidden>
                    {TICK_VALUES.map((v) => (
                        <span
                            key={v}
                            className="iot-aqi-scale-tick"
                            style={{ left: `${((v - TEMP_MIN) / span) * 100}%` }}
                        >
                            {v}
                        </span>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default IotTempEducational;
