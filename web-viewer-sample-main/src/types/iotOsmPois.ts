/**
 * Baked OSM POIs for Kit (`iotOsmPoisStations` message).
 * Source: `kit-app-template-main/source/data/osm/osm_pois_gbg.json`
 */

export const IOT_OSM_POI_CATEGORY_ORDER = [
    'restaurants',
    'cafes_bars',
    'parks',
    'culture',
    'transit_stops',
] as const;

export type IotOsmPoiCategory = (typeof IOT_OSM_POI_CATEGORY_ORDER)[number];

export const IOT_OSM_POI_CATEGORY_LABELS: Record<IotOsmPoiCategory, string> = {
    restaurants: 'Restaurants',
    cafes_bars: 'Cafés & bars',
    parks: 'Parks',
    culture: 'Culture',
    transit_stops: 'Transit stops',
};

export interface IotOsmPoiStation {
    id: string;
    lat: number;
    lon: number;
    name: string;
    category: IotOsmPoiCategory;
    /** metres from bake reference — list UI only */
    distance_m?: number;
    opening_hours?: string;
    detail?: string;
}
