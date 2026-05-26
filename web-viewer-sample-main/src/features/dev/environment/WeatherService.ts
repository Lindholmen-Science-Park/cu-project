export type WeatherData = {
  city: string;
  temperature: number;
  description: string;
  isRaining: boolean;
  rainIntensity: number; // 0-1 scale
  icon: string;
};

/**
 * Demo weather service. Replace with real API calls as needed.
 */
export class WeatherService {
  static async getCurrentWeather(): Promise<WeatherData> {
    // Simulate a call latency
    await new Promise((r) => setTimeout(r, 300));

    // Demo payload (Göteborg)
    return {
      city: 'Göteborg',
      temperature: 12,
      description: 'Partly cloudy',
      isRaining: Math.random() > 0.6,
      rainIntensity: Math.random(),
      icon: '⛅',
    };
  }
}


