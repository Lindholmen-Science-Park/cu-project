/**
 * Normalized air-quality station for Kit (`iotAirQualityStations` message).
 * WGS84 lat/lon; `aqi` is US AQI or -1 if unknown.
 */
export interface IotAirQualityStation {
    id: string;
    name: string;
    lat: number;
    lon: number;
    aqi: number;
    pm25?: number;
    /** WAQI `iaqi.t` — outdoor °C when station reports it */
    tempC?: number;
    time?: string;
}

export interface IotAirQualityStationsPayload {
    stations: IotAirQualityStation[];
}
