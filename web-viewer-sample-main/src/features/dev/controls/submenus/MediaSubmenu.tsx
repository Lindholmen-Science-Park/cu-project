import React from 'react';
import { useControl } from '../../../streaming/contexts';

interface Props {
    closeMenu: () => void;
}

const MediaSubmenu: React.FC<Props> = ({ closeMenu }) => {
    const ctrl = useControl();
    const onPlayVideo = ctrl.handlePlayVideo;

    return (
        <div className="controls-submenu">
            <button className="controls-submenu-back" onClick={() => closeMenu()}>‹ Back</button>
            <h3 className="controls-menu-title">Media</h3>

            <h4 className="controls-subtitle">Video</h4>
            <div className="controls-menu-buttons">
                {onPlayVideo && (
                    <button className="controls-menu-button" onClick={() => { onPlayVideo(); closeMenu(); }}>
                        <div className="controls-button-icon">▶️</div><span>Play Video</span>
                    </button>
                )}
            </div>
            <p className="controls-menu-hint">Play pre-rendered video content on top of the scene.</p>
        </div>
    );
};

export default MediaSubmenu;
