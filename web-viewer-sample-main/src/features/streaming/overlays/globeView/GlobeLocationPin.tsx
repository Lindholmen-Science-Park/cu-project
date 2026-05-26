import React, { useMemo } from 'react';
import { Entity, BillboardGraphics, LabelGraphics } from 'resium';
import { Cartesian3, Cartesian2, Color, VerticalOrigin, HorizontalOrigin, NearFarScalar } from 'cesium';

export interface GlobeLocation {
    id: string;
    labelKey: string;
    fallbackLabel: string;
    lat: number;
    lon: number;
    targetView: string;
    scene?: string;
    transitionMessageKey: string;
    cameraFlight: {
        waypoints: { lat: number; lon: number; alt: number; duration: number; heading?: number; pitch?: number; maxHeight?: number }[];
    };
}

interface Props {
    location: GlobeLocation;
    label: string;
    visible: boolean;
    onClick: (location: GlobeLocation) => void;
}

const PIN_SVG = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`
<svg xmlns="http://www.w3.org/2000/svg" width="48" height="64" viewBox="0 0 48 64">
  <defs>
    <filter id="s" x="-20%" y="-10%" width="140%" height="130%">
      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.4"/>
    </filter>
  </defs>
  <path d="M24 4C13.5 4 5 12.5 5 23c0 14 19 37 19 37s19-23 19-37C43 12.5 34.5 4 24 4z"
        fill="#76b900" stroke="#fff" stroke-width="2" filter="url(#s)"/>
  <circle cx="24" cy="22" r="8" fill="#fff"/>
</svg>
`)}`;

const GlobeLocationPin: React.FC<Props> = ({ location, label, visible, onClick }) => {
    const position = useMemo(
        () => Cartesian3.fromDegrees(location.lon, location.lat, 50),
        [location.lat, location.lon],
    );

    if (!visible) return null;

    return (
        <Entity
            position={position}
            onClick={() => onClick(location)}
            name={label}
        >
            <BillboardGraphics
                image={PIN_SVG}
                width={36}
                height={48}
                verticalOrigin={VerticalOrigin.BOTTOM}
                scaleByDistance={new NearFarScalar(500, 1.4, 50000, 0.4)}
            />
            <LabelGraphics
                text={label}
                font="bold 26px sans-serif"
                fillColor={Color.WHITE}
                outlineColor={Color.BLACK}
                outlineWidth={2}
                verticalOrigin={VerticalOrigin.BOTTOM}
                horizontalOrigin={HorizontalOrigin.CENTER}
                pixelOffset={new Cartesian2(0, -36)}
                scaleByDistance={new NearFarScalar(500, 1.2, 50000, 0.4)}
                showBackground
                backgroundColor={new Color(0, 0, 0, 0.6)}
                backgroundPadding={new Cartesian2(10, 5)}
            />
        </Entity>
    );
};

export default GlobeLocationPin;
