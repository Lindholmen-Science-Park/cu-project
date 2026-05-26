import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useControl, useEnvironment, useNavigation, useStream } from '../../contexts';
import { computeVideoContentRect, type ContentRect } from '../overlayUtils';
import { useSmoothedOverlayPosition } from '../useSmoothedOverlayPosition';
import flagPennantUrl from '@icons/navigation/flag-pennant.svg';
import mapPinUrl from '@icons/map-markers/MapPinSimpleArea.svg';
import './BirdEyeRouteOverlay.css';

const VIDEO_ID = 'remote-video';

function BirdEyeRouteBubble({
    className,
    targetX,
    targetY,
    children,
}: {
    className: string;
    targetX: number;
    targetY: number;
    children: React.ReactNode;
}) {
    const { x, y } = useSmoothedOverlayPosition(targetX, targetY);
    return (
        <div className={className} style={{ left: x, top: y }}>
            {children}
        </div>
    );
}

/**
 * Bird's-eye dashed route from Kit (`birdEyeRouteOverlay` → `birdEyeRoutePoints`).
 * Endpoint bubbles (flag + map pin) show during map-marker "Get directions" preview.
 */
const BirdEyeRouteOverlay: React.FC = () => {
    const ctrl = useControl();
    const env = useEnvironment();
    const nav = useNavigation();
    const stream = useStream();
    const rootRef = useRef<HTMLDivElement | null>(null);
    const [contentRect, setContentRect] = useState<ContentRect | null>(null);

    const data = ctrl.birdEyeRoutePoints;
    const directionsPreview =
        nav.mapMarkerDirectionsPreview != null && !nav.movingToPoiId;
    // When the user flips the start/end inputs in the directions panel, the
    // panel-side icons swap. The map markers must follow so the same
    // semantics ("which end is the destination") are presented consistently.
    // The route polyline is always Kit's first→last path, so we just swap
    // which icon goes on which endpoint without touching the geometry.
    const swapped = nav.mapMarkerDirectionsSwapped;

    useEffect(() => {
        const video = document.getElementById(VIDEO_ID) as HTMLVideoElement | null;
        if (!video) return;

        let raf = 0;
        const refresh = () => {
            try {
                setContentRect(computeVideoContentRect(video));
            } catch {
                setContentRect(null);
            }
        };
        const onResize = () => {
            cancelAnimationFrame(raf);
            raf = requestAnimationFrame(refresh);
        };
        refresh();
        window.addEventListener('resize', onResize);
        video.addEventListener('loadedmetadata', onResize);
        video.addEventListener('resize', onResize as any);
        return () => {
            cancelAnimationFrame(raf);
            window.removeEventListener('resize', onResize);
            video.removeEventListener('loadedmetadata', onResize);
            video.removeEventListener('resize', onResize as any);
        };
    }, []);

    useEffect(() => {
        if (!data?.points?.length) return;
        const video = document.getElementById(VIDEO_ID) as HTMLVideoElement | null;
        if (!video) return;
        try {
            setContentRect(computeVideoContentRect(video));
        } catch {
            /* ignore */
        }
    }, [data?.points, data?.viewport]);

    const layout = useMemo(() => {
        if (
            stream.sceneLoading ||
            env.currentCamera !== 'bird_eye' ||
            !data ||
            !data.viewport ||
            data.viewport.width <= 0 ||
            data.viewport.height <= 0 ||
            !contentRect
        ) {
            return null;
        }

        const navPts = data.points ?? [];
        const osmPts = data.osmPoints ?? [];
        const pinMarker = data.pinMarker ?? null;
        // Require at least one drawable polyline (a segment needs ≥2
        // points) OR a solo pin marker (pin sheet before directions).
        const hasNav = navPts.length >= 2;
        const hasOsm = osmPts.length >= 2;
        const hasAnyPoly = hasNav || hasOsm;
        if (!hasAnyPoly && !pinMarker) return null;

        const vp = data.viewport;
        const rootRect = rootRef.current?.getBoundingClientRect() ?? { left: 0, top: 0 };

        const mapPt = (sx: number, sy: number) => {
            const xClient = contentRect.left + (sx / vp.width) * contentRect.width;
            const yClient = contentRect.top + (sy / vp.height) * contentRect.height;
            return { x: xClient - rootRect.left, y: yClient - rootRect.top };
        };

        const navMapped = hasNav ? navPts.map((p) => mapPt(p.sx, p.sy)) : [];
        const osmMapped = hasOsm ? osmPts.map((p) => mapPt(p.sx, p.sy)) : [];

        const navPoly = hasNav ? navMapped.map((p) => `${p.x},${p.y}`).join(' ') : '';
        const osmPoly = hasOsm ? osmMapped.map((p) => `${p.x},${p.y}`).join(' ') : '';

        // Endpoint bubbles anchor to the composed polyline's true
        // first/last vertex. Kit ships those explicitly as
        // ``startMarker`` / ``endMarker`` so we pin the correct
        // endpoints regardless of leg order — picking from the
        // separate nav/osm arrays misplaces the start bubble on
        // OSM→NavMesh and cross-island routes (``navMapped[0]`` is
        // the bridge handover point, not the user's actual start).
        // Fall back to the leg-arrays heuristic if Kit is an older
        // version that did not yet ship the markers.
        const startExplicit = data.startMarker ? mapPt(data.startMarker.sx, data.startMarker.sy) : null;
        const endExplicit = data.endMarker ? mapPt(data.endMarker.sx, data.endMarker.sy) : null;
        const first = hasAnyPoly
            ? startExplicit ?? (hasNav ? navMapped[0] : osmMapped[0])
            : null;
        const last = hasAnyPoly
            ? endExplicit ?? (hasOsm ? osmMapped[osmMapped.length - 1] : navMapped[navMapped.length - 1])
            : null;

        // Pin-only mode: no polyline (pin sheet is open, Get directions
        // not clicked yet). Render a single flag bubble at the projected
        // pin position so the user sees where they tapped. The player
        // marker continues to show via the userLocation projectable.
        const pinOnly = !hasAnyPoly && pinMarker !== null;
        const pinMapped = pinMarker ? mapPt(pinMarker.sx, pinMarker.sy) : null;

        return {
            navPoly,
            osmPoly,
            first,
            last,
            showBubbles: hasAnyPoly && directionsPreview,
            pinOnly,
            pinMapped,
        };
    }, [stream.sceneLoading, env.currentCamera, data, contentRect, directionsPreview]);

    if (!layout) return null;

    const showRouteBubbles = layout.showBubbles && layout.first && layout.last;
    const showPinOnly = layout.pinOnly && layout.pinMapped;
    const ariaHidden = !showRouteBubbles && !showPinOnly;

    return (
        <div ref={rootRef} className="bird-eye-route-overlay" aria-hidden={ariaHidden}>
            <svg className="bird-eye-route-overlay__svg" width="100%" height="100%">
                {layout.navPoly ? (
                    <polyline
                        className="bird-eye-route-overlay__track"
                        fill="none"
                        points={layout.navPoly}
                    />
                ) : null}
                {layout.osmPoly ? (
                    <polyline
                        className="bird-eye-route-overlay__track bird-eye-route-overlay__track--osm"
                        fill="none"
                        points={layout.osmPoly}
                    />
                ) : null}
            </svg>
            {showRouteBubbles ? (
                <>
                    <BirdEyeRouteBubble
                        className="bird-eye-route-bubble bird-eye-route-bubble--start"
                        targetX={layout.first!.x}
                        targetY={layout.first!.y}
                    >
                        <img
                            src={swapped ? flagPennantUrl : mapPinUrl}
                            alt=""
                            width={22}
                            height={22}
                            draggable={false}
                        />
                        <span className="bird-eye-route-bubble__pointer" aria-hidden />
                        <span className="bird-eye-route-bubble__ground" aria-hidden>
                            <span className="bird-eye-route-bubble__ground-dot" />
                        </span>
                    </BirdEyeRouteBubble>
                    <BirdEyeRouteBubble
                        className="bird-eye-route-bubble bird-eye-route-bubble--destination"
                        targetX={layout.last!.x}
                        targetY={layout.last!.y}
                    >
                        <img
                            src={swapped ? mapPinUrl : flagPennantUrl}
                            alt=""
                            width={22}
                            height={22}
                            draggable={false}
                        />
                        <span className="bird-eye-route-bubble__pointer" aria-hidden />
                    </BirdEyeRouteBubble>
                </>
            ) : null}
            {showPinOnly ? (
                // Pin sheet is open, Get directions not pressed yet —
                // render the destination flag without any polyline. The
                // player marker continues to show via the userLocation
                // projectable (InteractionBoxesOverlay).
                <BirdEyeRouteBubble
                    className="bird-eye-route-bubble bird-eye-route-bubble--destination"
                    targetX={layout.pinMapped!.x}
                    targetY={layout.pinMapped!.y}
                >
                    <img
                        src={flagPennantUrl}
                        alt=""
                        width={22}
                        height={22}
                        draggable={false}
                    />
                    <span className="bird-eye-route-bubble__pointer" aria-hidden />
                </BirdEyeRouteBubble>
            ) : null}
        </div>
    );
};

export default BirdEyeRouteOverlay;
