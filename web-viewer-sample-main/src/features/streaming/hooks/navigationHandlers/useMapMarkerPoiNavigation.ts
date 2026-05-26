import { useState, useCallback } from 'react';

/** Bird's-eye map marker → same POI sheet UX as search/restroom (see MapMarkerPoiSheet). */
export type MapMarkerSheetData = {
    id: string;
    title: string;
    spawnPoint: string;
    primPath: string;
    isAccessible?: boolean;
    /**
     * Ad-hoc "pin anywhere" pin dispatched by Kit's `birdEyePinSheet`. When
     * true, `worldPos` holds the snapped coordinate and the sheet uses
     * world-position routing/teleport instead of `primPath`/`spawnPoint`.
     */
    isAdHocPin?: boolean;
    worldPos?: { x: number; y: number; z: number };
    /**
     * False when the pin landed outside the navmesh. Only used by the
     * pin sheet to gate the teleport button — outside pins can still
     * be navigated to (the Kit-side `RouteComposer` composes a
     * NavMesh+OSM path), but teleporting would drop the player in
     * dead geometry with no navmesh to move on.
     */
    isInsideNavmesh?: boolean;
    /** Internal magnet name (`nav_waypoint_A`, `PlayerSpawnPoint_Foyer`…); empty when no magnet snapped. */
    magnetName?: string;
    /**
     * Set when the destination is a navmesh POI (e.g. a restroom or quiet
     * zone) that has no `PlayerSpawnPoint_*` companion. The sheet uses
     * `poiTeleport { primPath }` instead of `teleportToSpawnpoint` for the
     * teleport button, and the directions panel swap ships
     * `startEndpointPath: primPath` so Kit teleports to the prim's xform.
     * NavMesh+OSM routing to/from the POI is composed server-side by the
     * `RouteComposer`, so no OSM preview coords need to travel through
     * the web layer.
     */
    useNavmeshPoiTeleport?: boolean;
};

export function useMapMarkerPoiNavigation() {
    const [mapMarkerSheet, setMapMarkerSheet] = useState<MapMarkerSheetData | null>(null);
    /** Bird’s-eye pin highlight when sheet open (POI) or “Find my seat” seat panel open (arena marker). */
    const [birdEyeMapMarkerFocusId, setBirdEyeMapMarkerFocusId] = useState<string | null>(null);

    const openMapMarkerSheet = useCallback((data: MapMarkerSheetData) => {
        setMapMarkerSheet(data);
        setBirdEyeMapMarkerFocusId(data.id);
    }, []);

    const closeMapMarkerSheet = useCallback(() => {
        setMapMarkerSheet(null);
        setBirdEyeMapMarkerFocusId(null);
    }, []);

    /** Arena / “Find my seat” map pin — opens seat panel, not POI sheet. */
    const openFindMySeatFromBirdEyeMap = useCallback((markerId: string) => {
        setMapMarkerSheet(null);
        setBirdEyeMapMarkerFocusId(markerId);
    }, []);

    const clearBirdEyeMapMarkerFocus = useCallback(() => {
        setBirdEyeMapMarkerFocusId(null);
    }, []);

    return {
        mapMarkerSheet,
        openMapMarkerSheet,
        closeMapMarkerSheet,
        birdEyeMapMarkerFocusId,
        openFindMySeatFromBirdEyeMap,
        clearBirdEyeMapMarkerFocus,
    };
}
