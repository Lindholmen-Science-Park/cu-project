import React, { type ReactElement } from 'react';
import { useAppUI, useStream } from './contexts';
import WeatherOverlay from './overlays/weather/WeatherOverlay';
import { InteractionBoxesOverlay } from './overlays/interactionBoxes/InteractionBoxesOverlay';
import NpcBubbleOverlay from './overlays/npcBubble/NpcBubbleOverlay';
import IconBubbleOverlay from './overlays/iconBubble/IconBubbleOverlay';
import AvatarChatOverlay from './overlays/avatarChat/AvatarChatOverlay';
import VideoPlayerOverlay from './overlays/videoPlayer/VideoPlayerOverlay';
import SpatialSoundOverlay from './overlays/spatialSound/SpatialSoundOverlay';
import Video360Overlay from './overlays/video360/Video360Overlay';
import VideoBookOverlay from '../cu/videobook/VideoBookOverlay';
import TriggerZoneToast from './components/TriggerZoneToast';
import SceneLoadingOverlay from './components/SceneLoadingOverlay';
import IotAirStationsPanel from './overlays/iotAirQuality/IotAirStationsPanel';
import IotBikeSharePanel from './overlays/iotBikeShare/IotBikeSharePanel';
import IotTransitLivePanel from './overlays/iotTransitLive/IotTransitLivePanel';
import IotOsmPoisPanel from './overlays/iotOsmPois/IotOsmPoisPanel';
interface SharedOverlayLayerProps {
    viewTransitionOverlay: ReactElement | null;
}

const SharedOverlayLayer: React.FC<SharedOverlayLayerProps> = ({ viewTransitionOverlay }) => {
    const stream = useStream();
    const appUI = useAppUI();

    if (appUI.seatArrivalCelebrationVisible || appUI.poiArrivalVisible) return null;

    return (
        <>
            <WeatherOverlay />

            <InteractionBoxesOverlay />

            <NpcBubbleOverlay />

            <IconBubbleOverlay />

            <VideoBookOverlay />

            <SpatialSoundOverlay />

            <Video360Overlay />

            <AvatarChatOverlay />

            <VideoPlayerOverlay />

            <TriggerZoneToast />

            <IotAirStationsPanel />

            <IotBikeSharePanel />

            <IotTransitLivePanel />

            <IotOsmPoisPanel />

            <SceneLoadingOverlay />

            {stream.streamReady ? viewTransitionOverlay : null}
        </>
    );
};

export default SharedOverlayLayer;
