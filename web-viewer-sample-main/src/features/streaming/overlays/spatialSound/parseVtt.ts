/**
 * Minimal WebVTT parser for the Spatial Sound Overlay.
 *
 * The overlay drives audio via the Web Audio API directly (not through an
 * `<audio>` / `<video>` element), so we cannot lean on the browser's native
 * `<track>` machinery for caption rendering. We do the parsing ourselves once
 * on load and look up the active cue per animation frame.
 *
 * We deliberately support only the subset of the WebVTT spec we actually use:
 * timestamps `HH:MM:SS.mmm` (or `MM:SS.mmm`), one or more text lines per cue,
 * blank lines separating cues, and an optional cue identifier. NOTE block,
 * cue settings (positioning), and styling tags are stripped or ignored — they
 * have no meaning in our overlay layout.
 *
 * Returns cues already sorted by `startSec` so consumers can short-circuit
 * the active-cue scan.
 */

export interface VttCue {
    startSec: number;
    endSec: number;
    text: string;
}

const TIMESTAMP_LINE = /^(\d{1,2}:)?(\d{1,2}):(\d{2})\.(\d{1,3})\s*-->\s*(\d{1,2}:)?(\d{1,2}):(\d{2})\.(\d{1,3})/;

function parseTimestamp(hour: string | undefined, min: string, sec: string, ms: string): number {
    const h = hour ? parseInt(hour.replace(':', ''), 10) : 0;
    const m = parseInt(min, 10);
    const s = parseInt(sec, 10);
    const f = parseInt((ms + '00').slice(0, 3), 10);
    return h * 3600 + m * 60 + s + f / 1000;
}

export function parseVtt(source: string): VttCue[] {
    const cues: VttCue[] = [];
    if (!source) return cues;

    const normalized = source.replace(/\r\n?/g, '\n');
    const blocks = normalized.split(/\n\n+/);

    for (const block of blocks) {
        const lines = block.split('\n').filter((ln) => ln.length > 0);
        if (lines.length === 0) continue;

        // Skip the WEBVTT header and any NOTE blocks
        if (/^WEBVTT(\s|$)/.test(lines[0])) continue;
        if (/^NOTE(\s|$)/.test(lines[0])) continue;

        let timingIdx = 0;
        if (!TIMESTAMP_LINE.test(lines[0])) {
            // First line is a cue identifier; timing is on line 2
            timingIdx = 1;
        }
        if (timingIdx >= lines.length) continue;

        const m = TIMESTAMP_LINE.exec(lines[timingIdx]);
        if (!m) continue;

        const startSec = parseTimestamp(m[1], m[2], m[3], m[4]);
        const endSec = parseTimestamp(m[5], m[6], m[7], m[8]);
        if (!Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec <= startSec) continue;

        const text = lines.slice(timingIdx + 1)
            .join('\n')
            // Strip simple WebVTT tags (<v Name>, <c.classname>, <i>, <b>, etc.)
            .replace(/<[^>]+>/g, '')
            .trim();
        if (!text) continue;

        cues.push({ startSec, endSec, text });
    }

    cues.sort((a, b) => a.startSec - b.startSec);
    return cues;
}

/**
 * Binary-search the active cue at `timeSec`, or return null if none is active.
 *
 * Cues are assumed sorted by `startSec` (parseVtt guarantees this). Cues may
 * overlap in pathological VTTs — we return the first one whose window covers
 * the given time, which matches the browser's native `<track>` behaviour.
 */
export function findActiveCue(cues: VttCue[], timeSec: number): VttCue | null {
    if (!cues.length) return null;

    let lo = 0;
    let hi = cues.length - 1;
    let candidate: VttCue | null = null;

    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const cue = cues[mid];
        if (cue.startSec > timeSec) {
            hi = mid - 1;
        } else {
            candidate = cue;
            lo = mid + 1;
        }
    }

    if (candidate && candidate.endSec >= timeSec && candidate.startSec <= timeSec) {
        return candidate;
    }
    return null;
}
