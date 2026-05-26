import React from 'react';

import sunHorizonRaw from '@icons/weather-season/sun-horizon.svg?raw';
import weatherRainRaw from '@icons/weather-season/weather-rain.svg?raw';
import weatherFogRaw from '@icons/weather-season/weather-fog.svg?raw';
import seasonSnowflakeRaw from '@icons/weather-season/season-snowflake.svg?raw';
import seasonSunRaw from '@icons/weather-season/season-sun.svg?raw';
import seasonTulipRaw from '@icons/weather-season/season-tulip.svg?raw';
import seasonLeafRaw from '@icons/weather-season/season-leaf.svg?raw';

const iconClass = 'cu-weather-btn-icon';

/** Figma exports use fixed purple — swap so pressed / dark mode follow `color` on the button */
function svgUseCurrentColor(raw: string): string {
    return raw
        .replace(/fill="#351A84"/gi, 'fill="currentColor"')
        .replace(/fill="#351a84"/gi, 'fill="currentColor"')
        .replace(/stroke="#351A84"/gi, 'stroke="currentColor"')
        .replace(/stroke="#351a84"/gi, 'stroke="currentColor"');
}

const SvgFromWorld3d: React.FC<{ raw: string }> = ({ raw }) => (
    <span className={`${iconClass} cu-weather-btn-svg-html`} dangerouslySetInnerHTML={{ __html: svgUseCurrentColor(raw) }} aria-hidden={true} />
);

export const CloudSunIcon: React.FC = () => <SvgFromWorld3d raw={sunHorizonRaw} />;

export const CloudRainIcon: React.FC = () => <SvgFromWorld3d raw={weatherRainRaw} />;

export const CloudFogIcon: React.FC = () => <SvgFromWorld3d raw={weatherFogRaw} />;

export const CloudSnowIcon: React.FC = () => <SvgFromWorld3d raw={seasonSnowflakeRaw} />;

export const SeasonSummerIcon: React.FC = () => <SvgFromWorld3d raw={seasonSunRaw} />;

export const SeasonSpringIcon: React.FC = () => <SvgFromWorld3d raw={seasonTulipRaw} />;

export const SeasonAutumnIcon: React.FC = () => <SvgFromWorld3d raw={seasonLeafRaw} />;

export const SeasonWinterIcon: React.FC = () => <SvgFromWorld3d raw={seasonSnowflakeRaw} />;
