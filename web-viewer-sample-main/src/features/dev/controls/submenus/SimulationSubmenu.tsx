import React from 'react';
import { useControl } from '../../../streaming/contexts';

interface Props {
    closeMenu: () => void;
}

const SimulationSubmenu: React.FC<Props> = ({ closeMenu }) => {
    const ctrl = useControl();

    const peopleVisible = ctrl.peopleVisible;
    const onPeopleToggle = ctrl.handlePeopleToggle;
    const lightCullingEnabled = ctrl.lightCullingEnabled;
    const onLightCullingToggle = ctrl.handleLightCullingToggle;
    const tileCullingEnabled = ctrl.tileCullingEnabled;
    const onTileCullingToggle = ctrl.handleTileCullingToggle;
    const stadiumLodLight = ctrl.stadiumLodLight;
    const onStadiumLodToggle = ctrl.handleStadiumLodToggle;
    const npcTestActive = ctrl.npcTestActive;
    const onNpcTestToggle = ctrl.handleNpcTestToggle;
    const maintenanceBotsActive = ctrl.maintenanceBotsActive;
    const onMaintenanceBotsToggle = ctrl.handleMaintenanceBotsToggle;

    return (
        <div className="controls-submenu">
            <button className="controls-submenu-back" onClick={() => closeMenu()}>‹ Back</button>
            <h3 className="controls-menu-title">Simulation</h3>

            <div className="controls-menu-buttons">
                <button className={`controls-menu-button ${peopleVisible ? 'active' : ''}`} onClick={() => { onPeopleToggle(); closeMenu(); }}>
                    <div className="controls-button-icon">{peopleVisible ? '🚶' : '👥'}</div><span>{peopleVisible ? 'Hide People' : 'Show People'}</span>
                </button>
                <button className={`controls-menu-button ${lightCullingEnabled ? 'active' : ''}`} onClick={() => { onLightCullingToggle(); closeMenu(); }}>
                    <div className="controls-button-icon">{lightCullingEnabled ? '💡' : '🔦'}</div><span>{lightCullingEnabled ? 'Disable Light Culling' : 'Enable Light Culling'}</span>
                </button>
                <button className={`controls-menu-button ${tileCullingEnabled ? 'active' : ''}`} onClick={() => { onTileCullingToggle(); closeMenu(); }}>
                    <div className="controls-button-icon">{tileCullingEnabled ? '🏙️' : '🏗️'}</div><span>{tileCullingEnabled ? 'Disable Tile Culling' : 'Enable Tile Culling'}</span>
                </button>
                <button className={`controls-menu-button ${stadiumLodLight ? 'active' : ''}`} onClick={() => { onStadiumLodToggle(); closeMenu(); }}>
                    <div className="controls-button-icon">{stadiumLodLight ? '🏟️' : '🏠'}</div><span>{stadiumLodLight ? 'Stadium: Full Detail' : 'Stadium: Light LOD'}</span>
                </button>
                <button className={`controls-menu-button ${npcTestActive ? 'active' : ''}`} onClick={() => { onNpcTestToggle(); closeMenu(); }}>
                    <div className="controls-button-icon">{npcTestActive ? '⏹️' : '🚶'}</div><span>{npcTestActive ? 'Stop NPC' : 'Start NPC Walk'}</span>
                </button>
                {onMaintenanceBotsToggle && (
                    <button className={`controls-menu-button ${maintenanceBotsActive ? 'active' : ''}`} onClick={() => { onMaintenanceBotsToggle(); closeMenu(); }}>
                        <div className="controls-button-icon">{maintenanceBotsActive ? '⏹️' : '🤖'}</div><span>{maintenanceBotsActive ? 'Remove Bots' : 'Spawn Maintenance Bots'}</span>
                    </button>
                )}
            </div>
        </div>
    );
};

export default SimulationSubmenu;
