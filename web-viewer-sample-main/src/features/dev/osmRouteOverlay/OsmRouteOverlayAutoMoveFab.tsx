import React, { useCallback } from 'react';
import { useNavigation } from '../../streaming/contexts/NavigationContext';
import { useControl } from '../../streaming/contexts/ControlContext';
import { useEnvironment } from '../../streaming/contexts/EnvironmentContext';
import { sendMessage } from '../../streaming/messaging';
import seatNavPlayIcon from '@icons/seat-route/figma-5706-play.svg';
import seatNavPauseIcon from '@icons/seat-route/figma-april-pause.svg';

/**
 * Floating Play/Pause action button for the OSM route overlay.
 *
 * Mounted only when the dev OSM route overlay is visible AND the
 * player is currently *attached* to a route (Kit confirms via
 * `osmRouteOverlayAttached`) AND we're in point-click mode AND not
 * on the bird-eye / globe cameras (where the overlay's hit testing
 * doesn't apply). Pressing Play asks Kit to walk the player along
 * the route they're currently on, in the direction the camera is
 * pointing, until the next junction (degree ≥ 3) or dead-end. At a
 * junction the auto-mover stops, the FAB flips back to Play, and
 * the user either taps a different route to choose a direction or
 * presses Play again to continue straight on.
 *
 * Gating on `osmRouteOverlayAttached` doubles as visual feedback:
 * after every click, the button either appears (route hit, you're
 * now bound to the polyline) or disappears (NavMesh hit, you've
 * jumped off). This is the only reliable signal the user has that
 * tells "did my tap land on the route or did it fall through to
 * regular ground?" — without it, taps near a route that grazed the
 * NavMesh felt like the route was still pulling them.
 */
const OsmRouteOverlayAutoMoveFab: React.FC = () => {
    const nav = useNavigation();
    const ctrl = useControl();
    const env = useEnvironment();

    const visible =
        !!nav.osmRouteOverlayVisible &&
        !!nav.osmRouteOverlayAttached &&
        ctrl.controlMode === 'pointClick' &&
        env.currentCamera !== 'bird_eye' &&
        env.currentCamera !== 'space';

    const isMoving = !!nav.playerAutoMoveActive;

    const handleClick = useCallback(() => {
        if (isMoving) {
            try { sendMessage('osmRouteOverlayAutoMove', { action: 'stop' }); } catch {}
            // Optimistic: Kit will confirm via autoMoveStatus, but the
            // pause icon flipping back to Play instantly avoids the
            // "did the tap register?" feel on slow round-trips.
            nav.setPlayerAutoMoveActive(false);
        } else {
            try { sendMessage('osmRouteOverlayAutoMove', { action: 'play' }); } catch {}
            nav.setPlayerAutoMoveActive(true);
        }
    }, [isMoving, nav]);

    if (!visible) return null;

    return (
        <div className="stream-seat-nav-overlay" role="presentation">
            <button
                type="button"
                className="stream-seat-nav-overlay__btn"
                onClick={handleClick}
                title={isMoving ? 'Pause OSM route walk' : 'Walk to next junction'}
                aria-label={isMoving ? 'Pause auto-walk along OSM route' : 'Auto-walk to next junction along OSM route'}
            >
                <img
                    src={isMoving ? seatNavPauseIcon : seatNavPlayIcon}
                    alt=""
                    width={32}
                    height={32}
                    draggable={false}
                    className="stream-seat-nav-overlay__icon"
                />
            </button>
        </div>
    );
};

export default OsmRouteOverlayAutoMoveFab;
