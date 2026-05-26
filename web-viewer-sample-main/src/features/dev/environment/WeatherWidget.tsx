import React, { useState, useEffect } from 'react';
import { WeatherService, WeatherData } from './WeatherService';
import { useEnvironment, useStream } from '../../streaming/contexts';
import './WeatherWidget.css';

const WeatherWidget: React.FC = () => {
  const env = useEnvironment();
  const stream = useStream();

  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isVisible = stream.streamReady && env.showWeather;

  const fetchWeather = async () => {
    setLoading(true);
    setError(null);
    try {
      const weatherData = await WeatherService.getCurrentWeather();
      setWeather(weatherData);
      setLastUpdated(new Date());
      env.handleWeatherChange(weatherData);
    } catch (err) {
      console.error('Failed to fetch weather:', err);
      setError('Failed to fetch weather data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isVisible && !weather && !loading) {
      fetchWeather();
    }
  }, [isVisible, weather, loading]);

  useEffect(() => {
    if (error && isVisible) {
      const retryTimer = setTimeout(() => {
        console.log('Auto-retrying weather fetch after error...');
        fetchWeather();
      }, 5000);
      return () => clearTimeout(retryTimer);
    }
  }, [error, isVisible]);

  if (!isVisible) return null;

  return (
    <div className="weather-widget">
      <div className="weather-header">
        <h3 className="weather-title">Göteborg Weather</h3>
      </div>

      {error ? (
        <div className="weather-error">
          <div className="error-icon">⚠️</div>
          <div className="error-text">{error}</div>
        </div>
      ) : weather ? (
        <div className="weather-content">
          <div className="weather-main">
            <div className="weather-icon">{weather.icon}</div>
            <div className="weather-temp">{weather.temperature}°C</div>
          </div>

          <div className="weather-details">
            <div className="weather-condition">{weather.description}</div>
            <div className="weather-city">{weather.city}</div>
            {weather.isRaining && (
              <div className="rain-indicator">
                <span className="rain-icon">🌧️</span>
                <span className="rain-text">
                  {weather.rainIntensity > 0.7 ? 'Heavy Rain' :
                   weather.rainIntensity > 0.3 ? 'Rain' : 'Light Rain'}
                </span>
              </div>
            )}
            {lastUpdated && (
              <div className="weather-updated">
                Updated: {lastUpdated.toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="weather-loading">
          <div className="loading-spinner">⏳</div>
          <div className="loading-text">Loading weather...</div>
        </div>
      )}
    </div>
  );
};

export default WeatherWidget;
