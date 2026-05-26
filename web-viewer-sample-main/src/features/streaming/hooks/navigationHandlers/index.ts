import type { CameraType } from '../../types';
import { useNavmeshCore } from './useNavmeshCore';
import { useSpotNavigation } from './useSpotNavigation';
import { useSeatNavigation } from './useSeatNavigation';
import { useExitNavigation } from './useExitNavigation';
import { usePoiNavigation } from './usePoiNavigation';
import { useQuietZoneNavigation } from './useQuietZoneNavigation';
import { useOsmNavigation } from './useOsmNavigation';
import { useMapMarkerPoiNavigation } from './useMapMarkerPoiNavigation';

export function useNavigationHandlers(
    streamReady: boolean,
    currentCamera: CameraType,
    setCurrentCamera: (camera: CameraType) => void,
) {
    const core = useNavmeshCore(streamReady, currentCamera, setCurrentCamera);
    const spots = useSpotNavigation(core.navigationSpots, core.navigationSpotsRef);
    const seats = useSeatNavigation(
        core.setRouteMeasureByRouteId,
        core.revertWheelchairMode,
        core.markRouteCalculating,
    );
    const exits = useExitNavigation();
    const pois = usePoiNavigation(core.markRouteCalculating);
    const quietZones = useQuietZoneNavigation(core.markRouteCalculating);
    const osm = useOsmNavigation();
    const mapMarkerPoi = useMapMarkerPoiNavigation();

    return {
        ...core,
        ...spots,
        ...seats,
        ...exits,
        ...pois,
        ...quietZones,
        ...osm,
        ...mapMarkerPoi,
    };
}
