export const TRAFFIC_SLIDER_DEBOUNCE_MS = 150;
export const JOYSTICK_INPUT_THROTTLE_MS = 33; // ~30 Hz
export const DEBUG_VERBOSE = false;
export const PRESET_COST_VALUE = 5;

export const FIXED_CAMERAS = [
    { id: 'camera_vip_entrance', label: 'VIP Entrance' },
    { id: 'camera_main_entrance_exit', label: 'Main Exit' },
    { id: 'camera_main_entrance_entry', label: 'Main Entry' },
];

let _messageSender: ((eventType: string, payload: Record<string, any>) => void) | null = null;

export function setMessageSender(fn: ((eventType: string, payload: Record<string, any>) => void) | null): void {
    _messageSender = fn;
}

export function sendMessage(eventType: string, payload: Record<string, any> = {}): void {
    _messageSender?.(eventType, payload);
}

export function shouldLogEvent(event: any): boolean {
    if (!event || typeof event !== 'object') return false;
    if (DEBUG_VERBOSE) return true;
    if (event.type === 'info' && event.title === 'unknown' && event.status === 100) return false;
    if (event.type === 'info' && event.detail && typeof event.detail === 'string') {
        if (event.detail.includes('##[') || (event.detail.includes('{') && event.detail.includes('}'))) return false;
    }
    if (event.event_type === 'uiInteractionBoxesUpdate') return false;
    if (event.event_type === 'birdEyeRouteOverlay') return false;
    return !!(event.event_type || event.action || event.type === 'error');
}
