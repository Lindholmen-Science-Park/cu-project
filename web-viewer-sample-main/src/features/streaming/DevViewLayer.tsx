import React from 'react';
import UIControls from '../dev/controls/UIControls';
import JoystickWidget from './widgets/JoystickWidget';
import WeatherWidget from '../dev/environment/WeatherWidget';
import EnvironmentalLightWidget from '../dev/environment/EnvironmentalLightWidget';
import DevWeatherSeasonPicker from '../dev/environment/DevWeatherSeasonPicker';
import UsdEditPanel from '../dev/controls/UsdEditPanel';
import MediaAdminPanel from '../dev/mediaAdmin/MediaAdminPanel';
import OsmRouteOverlayAutoMoveFab from '../dev/osmRouteOverlay/OsmRouteOverlayAutoMoveFab';
import { useControl, useStream } from './contexts';
import { useJoystickHandlers } from './hooks/useJoystickHandlers';

const DevViewLayer: React.FC = () => {
    const ctrl = useControl();
    const stream = useStream();
    const joystick = useJoystickHandlers(stream.streamReady, ctrl.controlMode);

    return (
        <>
            <UIControls />

            <JoystickWidget isVisible={stream.streamReady && ctrl.controlMode === 'joystick'} position="left" onJoystickChange={joystick.handleJoystickChange} />
            <JoystickWidget isVisible={stream.streamReady && ctrl.controlMode === 'joystick'} position="right" onJoystickChange={joystick.handleLookJoystickChange} />

            <WeatherWidget />
            <EnvironmentalLightWidget />
            <DevWeatherSeasonPicker />

            {ctrl.usdEditMode && <UsdEditPanel />}

            {ctrl.mediaAdminOpen && <MediaAdminPanel />}

            <OsmRouteOverlayAutoMoveFab />
        </>
    );
};

export default DevViewLayer;
