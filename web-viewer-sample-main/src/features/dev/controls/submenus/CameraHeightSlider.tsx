import React, { useCallback } from 'react';
import { useEnvironment } from '../../../streaming/contexts';

const DEFAULT_HEIGHT = 125;
const MIN_HEIGHT = 90;
const MAX_HEIGHT = 185;
const STEP = 1;

function heightLabel(cm: number): string {
    if (cm <= 100) return 'Wheelchair';
    if (cm <= 120) return "Child's view";
    if (cm <= 140) return 'Short';
    if (cm <= 160) return 'Average';
    if (cm <= 175) return 'Tall';
    return 'Very tall';
}

const CameraHeightSlider: React.FC = () => {
    const env = useEnvironment();
    const value = env.cameraHeight;
    const onHeightChange = env.handleCameraHeightChange;

    const handleReset = useCallback(() => {
        onHeightChange?.(DEFAULT_HEIGHT);
    }, [onHeightChange]);

    return (
        <>
            <h4 className="controls-subtitle controls-subtitle--camera-height-block">Camera Height</h4>
            <div className="speed-control">
                <div className="speed-slider-container">
                    <input
                        type="range"
                        min={MIN_HEIGHT}
                        max={MAX_HEIGHT}
                        step={STEP}
                        value={value}
                        onChange={(e) => onHeightChange?.(parseFloat(e.target.value))}
                        className="speed-slider"
                    />
                    <div className="speed-display">
                        <span className="speed-value">{value} cm</span>
                        <span className="speed-label">{heightLabel(value)}</span>
                    </div>
                </div>
                {value !== DEFAULT_HEIGHT && (
                    <button
                        type="button"
                        className="control-mode-btn control-mode-btn--camera-height-reset"
                        onClick={handleReset}
                    >
                        Reset to default ({DEFAULT_HEIGHT} cm)
                    </button>
                )}
            </div>
        </>
    );
};

export default CameraHeightSlider;
