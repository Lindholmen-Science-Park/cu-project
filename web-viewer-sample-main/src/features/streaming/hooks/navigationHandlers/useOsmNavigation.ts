import { useState, useCallback } from 'react';
import { sendMessage } from '../../messaging';
import type { OsmRouteInfo } from '../../types';

// Movement mode for dev City Navigate. Internal identifiers match the
// Kit-side NavMeshModeCache / RouteConfig.get_navmesh_mode vocabulary
// so the string passes through unchanged. Display labels live in the
// widget ("By foot" / "Wheelchair" / "Car").
export type OsmMode = 'walking' | 'wheelchair' | 'car';

export function useOsmNavigation() {
    const [osmNavigateOpen, setOsmNavigateOpen] = useState(false);
    const [osmSelectedPoiId, setOsmSelectedPoiId] = useState<string | null>(null);
    const [osmRouteInfo, setOsmRouteInfo] = useState<OsmRouteInfo | null>(null);
    const [osmMapVisible, setOsmMapVisible] = useState(false);
    const [osmSelectedMode, setOsmSelectedMode] = useState<OsmMode>('walking');

    const handleOsmPoiSelect = useCallback((poiId: string) => {
        setOsmSelectedPoiId(poiId);
        setOsmRouteInfo(null);
        sendMessage('osmNavigateSetPoi', { poiId });
    }, []);

    const handleOsmModeSelect = useCallback((mode: OsmMode) => {
        setOsmSelectedMode(mode);
        // Kit stores the last click internally; sending the mode alone
        // is enough for it to recompute the current route (if any) and
        // honour the mode on the next pick if no route is drawn yet.
        sendMessage('osmNavigateSetMode', { mode });
    }, []);

    const handleOsmClear = useCallback(() => {
        setOsmSelectedPoiId(null);
        setOsmRouteInfo(null);
        setOsmMapVisible(false);
        setOsmSelectedMode('walking');
        sendMessage('osmNavigateClear', {});
    }, []);

    const handleOsmNavigateClose = useCallback(() => {
        setOsmNavigateOpen(false);
        setOsmSelectedPoiId(null);
        setOsmRouteInfo(null);
        setOsmMapVisible(false);
        setOsmSelectedMode('walking');
        sendMessage('osmNavigateClear', {});
    }, []);

    const handleOsmToggleMap = useCallback(() => {
        const next = !osmMapVisible;
        setOsmMapVisible(next);
        sendMessage('osmNavigateToggleMap', { visible: next });
    }, [osmMapVisible]);

    return {
        osmNavigateOpen, setOsmNavigateOpen,
        osmSelectedPoiId, setOsmSelectedPoiId,
        osmRouteInfo, setOsmRouteInfo,
        osmMapVisible,
        osmSelectedMode,
        handleOsmPoiSelect,
        handleOsmModeSelect,
        handleOsmClear,
        handleOsmNavigateClose,
        handleOsmToggleMap,
    };
}
