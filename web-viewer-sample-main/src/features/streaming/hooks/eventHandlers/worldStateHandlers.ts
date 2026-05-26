import type { EventStateSetters } from './types';
import type { WeatherOption, SeasonOption } from '../../../cu/types';
import { notifyViewTransitionKitReady } from '../../viewTransition';
import { getAmbientSoundEngine, type SoundEmitter, type PlayerPose } from '../../audio/ambientSoundEngine';

const PRESET_TO_WEATHER: Record<string, WeatherOption> = {
    partlyCloudy: 'sun',
    clearSky: 'sun',
    cloudy: 'sun',
    overcast: 'sun',
    rainy: 'rain',
    darkStorm: 'rain',
    foggy: 'fog',
    snowy: 'snow',
    lightSnow: 'snow',
    heavySnow: 'snow',
};

function dayOfYearToSeason(day: number): SeasonOption {
    if (day >= 60 && day < 152) return 'spring';
    if (day >= 152 && day < 244) return 'summer';
    if (day >= 244 && day < 335) return 'autumn';
    return 'winter';
}

export function handleWorldStateEvents(event: any, s: EventStateSetters): boolean {
    if (event.event_type === 'seasonChangeStarted') {
        return true;
    }
    if (event.event_type === 'seasonChangeCompleted') {
        notifyViewTransitionKitReady();
        return true;
    }

    if (event.event_type === 'playerPose') {
        const p = event.payload ?? {};
        if (Array.isArray(p.pos) && Array.isArray(p.forward) && Array.isArray(p.up)) {
            getAmbientSoundEngine().updateListener({
                pos: [Number(p.pos[0]), Number(p.pos[1]), Number(p.pos[2])],
                forward: [Number(p.forward[0]), Number(p.forward[1]), Number(p.forward[2])],
                up: [Number(p.up[0]), Number(p.up[1]), Number(p.up[2])],
            } as PlayerPose);
        }
        return true;
    }

    if (event.event_type !== 'worldStateSync') return false;

    const p = event.payload ?? {};

    if (p.navmeshMode != null) s.setNavmeshMode(p.navmeshMode === 'wheelchair' ? 'wheelchair' : 'walking');
    if (p.navmeshBaking != null) s.setNavmeshBaking(!!p.navmeshBaking);
    if (p.peopleVisible != null) s.setPeopleVisible(!!p.peopleVisible);

    if (p.weatherPreset != null && s.setWeather) {
        const mapped = PRESET_TO_WEATHER[p.weatherPreset];
        if (mapped) s.setWeather(mapped);
    }
    if (p.season != null && s.setSeason) {
        const valid: SeasonOption[] = ['summer', 'spring', 'autumn', 'winter'];
        if (valid.includes(p.season as SeasonOption)) s.setSeason(p.season as SeasonOption);
    } else if (p.dayOfYear != null && s.setSeason) {
        s.setSeason(dayOfYearToSeason(Number(p.dayOfYear)));
    }
    if (p.timeOfDay != null && s.setTimeOfDayMinutes) {
        s.setTimeOfDayMinutes(Math.round(Number(p.timeOfDay) * 60));
    }

    if (p.cameraHeight != null && s.setCameraHeight) s.setCameraHeight(Number(p.cameraHeight));
    if (p.fogIntensity != null && s.setFogIntensity) s.setFogIntensity(Number(p.fogIntensity));
    if (p.timeOfDay != null && s.setTimeOfDay) s.setTimeOfDay(Number(p.timeOfDay));
    if (p.dayOfYear != null && s.setDayOfYear) s.setDayOfYear(Number(p.dayOfYear));
    if (p.cloudCoverage != null && s.setCloudCoverage) s.setCloudCoverage(Number(p.cloudCoverage));
    if (p.cumulusEnabled != null && s.setCumulusEnabled) s.setCumulusEnabled(!!p.cumulusEnabled);
    if (p.weatherPreset != null && s.setWeatherPreset) s.setWeatherPreset(String(p.weatherPreset));
    if (p.physicsState != null && s.setCurrentPhysics) s.setCurrentPhysics(p.physicsState === 'enabled' ? 'enabled' : 'disabled');

    if (p.cameraViewType != null) {
        const mapped = p.cameraViewType === 'firstPerson' ? 'first_person' : 'bird_eye';
        // Don't overwrite the web-only 'space' mode — Kit doesn't know about
        // it, and the user is currently in the globe overlay. The exit-back-
        // to-bird_eye flow already calls setCurrentCamera('bird_eye') from
        // handleCameraChange when the user clicks a pin.
        s.setCurrentCamera((cur) => (cur === 'space' ? cur : (mapped as any)));
    }

    if (p.movementSpeed != null && s.setMovementSpeed) s.setMovementSpeed(Number(p.movementSpeed));

    if (p.mediaContentTheme != null && s.setMediaContentTheme) {
        s.setMediaContentTheme(String(p.mediaContentTheme));
    }

    if (p.accessibilityDiffOverlayVisible !== undefined && p.accessibilityDiffOverlayVisible !== null && s.setAccessibilityDiffVisible) {
        s.setAccessibilityDiffVisible(!!p.accessibilityDiffOverlayVisible);
    }
    if (p.navmeshDebugOverlayVisible !== undefined && p.navmeshDebugOverlayVisible !== null && s.setNavmeshDebugOverlayVisible) {
        s.setNavmeshDebugOverlayVisible(!!p.navmeshDebugOverlayVisible);
    }

    if (Array.isArray(p.soundEmitters)) {
        const emitters: SoundEmitter[] = (p.soundEmitters as any[]).flatMap((e) => {
            if (!e || typeof e !== 'object') return [];
            const { id, file, pos } = e;
            if (typeof id !== 'string' || typeof file !== 'string' || !Array.isArray(pos) || pos.length < 3) return [];
            return [{
                id,
                file,
                pos: [Number(pos[0]), Number(pos[1]), Number(pos[2])],
                radius: e.radius != null ? Number(e.radius) : undefined,
                refDistance: e.refDistance != null ? Number(e.refDistance) : undefined,
                volume: e.volume != null ? Number(e.volume) : undefined,
                loop: e.loop != null ? !!e.loop : undefined,
                startDelaySec: e.startDelaySec != null ? Number(e.startDelaySec) : undefined,
            }];
        });
        getAmbientSoundEngine().setEmitters(emitters);
    }

    if (s.setFirstPersonLocation) {
        if (p.lastFirstPersonPosition != null && typeof p.lastFirstPersonPosition === 'object') {
            s.setFirstPersonLocation({
                x: Number(p.lastFirstPersonPosition.x),
                y: Number(p.lastFirstPersonPosition.y),
                z: Number(p.lastFirstPersonPosition.z),
            });
        } else if ('lastFirstPersonPosition' in p && p.lastFirstPersonPosition == null) {
            s.setFirstPersonLocation(null);
        }
    }

    return true;
}
