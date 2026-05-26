/**
 * Normalized bike-share dock for Kit (`iotBikeShareStations` message).
 * Dev-only; English UI strings live beside components (not customer i18n).
 */
export interface IotBikeShareStation {
    id: string;
    lat: number;
    lon: number;
    name: string;
    bikesAvailable: number;
    /** For Kit marker tint; from GBFS docks or `capacity - bikes` when capacity exists. */
    docksAvailable: number;
}
