/**
 * Safe wrapper for AppStreamer.stop() and AppStreamer.terminate().
 *
 * The library's stop() sets _disconnectStatus=1 and returns immediately with
 * status 'inProgress'. terminate() then checks _disconnectStatus !== 0 and
 * throws "Stream is already stopping", so _terminateStream() never runs and
 * _ragnarokApp stays alive. The next connect() finds _ragnarokApp and returns
 * "Stream already connected" without establishing a real WebRTC connection.
 *
 * After the fire-and-forget stop/terminate, we force-clear the library's
 * internal state so the next connect() always starts clean.
 */
import { AppStreamer } from '@nvidia/omniverse-webrtc-streaming-library';

export function safeTerminateStream(): void {
    try {
        const r = AppStreamer.stop();
        if (r && typeof (r as Promise<unknown>).catch === 'function') {
            (r as Promise<unknown>).catch(() => {});
        }
    } catch {}

    try {
        const r = AppStreamer.terminate();
        if (r && typeof (r as Promise<unknown>).catch === 'function') {
            (r as Promise<unknown>).catch(() => {});
        }
    } catch {}

    // Force-clear internal state so the next connect() creates a fresh instance.
    try {
        const stream = (AppStreamer as any)._stream;
        if (stream && stream._ragnarokApp) {
            try { stream._ragnarokApp.destroy(); } catch {}
            stream._ragnarokApp = null;
        }
    } catch {}
    try { (AppStreamer as any)._stream = null; } catch {}
    try { (AppStreamer as any)._disconnectStatus = 0; } catch {}
    try { (AppStreamer as any)._streamStatus = 0; } catch {}
}
