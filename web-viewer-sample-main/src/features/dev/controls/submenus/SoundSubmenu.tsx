import React, { useCallback } from 'react';
import { useEnvironment } from '../../../streaming/contexts';

interface Props {
    closeMenu: () => void;
}

const SoundSubmenu: React.FC<Props> = ({ closeMenu }) => {
    const env = useEnvironment();

    const soundAreasVisible = env.soundAreasVisible;
    const onSoundAreasToggle = env.handleSoundAreasToggle;
    const soundDataCalcActive = env.soundDataCalcActive;
    const soundDataCalcBaking = env.soundDataCalcBaking;
    const onSoundDataCalcToggle = env.handleSoundDataCalcToggle;
    const onOpenSoundCostWidget = useCallback(() => env.setSoundCostWidgetOpen(true), [env.setSoundCostWidgetOpen]);

    return (
        <div className="controls-submenu">
            <button className="controls-submenu-back" onClick={() => closeMenu()}>‹ Back</button>
            <h3 className="controls-menu-title">Sound</h3>

            {onSoundAreasToggle && (<>
                <h4 className="controls-subtitle">Sound Coverage</h4>
                <div className="control-mode-toggle">
                    <button className={`control-mode-btn ${!soundAreasVisible ? 'active' : ''}`} onClick={() => { if (soundAreasVisible) onSoundAreasToggle(); closeMenu(); }}>Off</button>
                    <button className={`control-mode-btn ${soundAreasVisible ? 'active' : ''}`} onClick={() => { if (!soundAreasVisible) onSoundAreasToggle(); closeMenu(); }}>Show Areas</button>
                </div>
            </>)}

            {onSoundDataCalcToggle && (<>
                <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Sound → Pathfinding</h4>
                <div className="control-mode-toggle">
                    <button className={`control-mode-btn ${!soundDataCalcActive ? 'active' : ''}`} disabled={soundDataCalcBaking} onClick={() => { if (soundDataCalcActive) onSoundDataCalcToggle(); }}>Off</button>
                    <button className={`control-mode-btn ${soundDataCalcActive ? 'active' : ''}`} disabled={soundDataCalcBaking} onClick={() => { if (!soundDataCalcActive) onSoundDataCalcToggle(); }}>Active</button>
                </div>
                {soundDataCalcBaking && <div className="navmesh-baking-indicator">Rebaking NavMesh with sound areas...</div>}
                {(soundDataCalcActive || soundAreasVisible) && onOpenSoundCostWidget != null && (
                    <button className="controls-menu-button" onClick={() => { onOpenSoundCostWidget(); closeMenu(); }} style={{ marginTop: 8 }}>
                        <div className="controls-button-icon">📊</div><span>Pathfinding costs…</span>
                    </button>
                )}
            </>)}
        </div>
    );
};

export default SoundSubmenu;
