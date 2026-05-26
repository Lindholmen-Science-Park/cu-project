import React from 'react';
import ExitsWidget from './widgets/ExitsWidget';
import RestroomWidget from './widgets/RestroomWidget';
import MapMarkerPoiSheet from './widgets/MapMarkerPoiSheet';
import MapMarkerDirectionsPanel from './widgets/MapMarkerDirectionsPanel';
import QuietZoneWidget from './widgets/QuietZoneWidget';
import SeatNavigateWidget from './widgets/SeatNavigateWidget';
import CameraPathfindingWidget from './widgets/CameraPathfindingWidget';
import SoundCostWidget from './widgets/SoundCostWidget';
import OsmNavigateWidget from './widgets/OsmNavigateWidget';

const SharedWidgetLayer: React.FC = () => {
    return (
        <>
            <ExitsWidget />
            <RestroomWidget />
            <MapMarkerPoiSheet />
            <MapMarkerDirectionsPanel />
            <QuietZoneWidget />
            <SeatNavigateWidget />
            <CameraPathfindingWidget />
            <SoundCostWidget />
            <OsmNavigateWidget />
        </>
    );
};

export default SharedWidgetLayer;
