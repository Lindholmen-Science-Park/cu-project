/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 */

/**
 * Shared SpeechSynthesis utilities for WCAG-compliant "Listen" buttons.
 *
 * Two axes are kept separate on purpose:
 *
 * 1. **Voice language** — must match the *language of the text being spoken*
 *    (WCAG 3.1.2 Language of Parts). Most spoken text is properly localized
 *    (i18n greetings, interaction-box titles, user-typed input), so the
 *    caller passes the UI language. The one exception is the AI chat reply
 *    in fr/es UIs: the AI backend only supports en/sv, so the *text* comes
 *    back in English and the caller must pass `'en'` so the voice matches
 *    the language of the words being read out.
 *
 * 2. **Voice character** (gender, rate, pitch, optional name hint) — driven by
 *    the speaker's `AvatarVoiceProfile`. This keeps a given character (e.g.
 *    Red) consistent across languages: female in English, female in Swedish,
 *    rather than collapsing to whatever the OS happened to ship as the default
 *    voice for that locale.
 *
 * Voice gender is treated as a *preference*, not a hard filter — many OSes
 * only ship one voice per locale, in which case we still speak the text with
 * that voice rather than silently failing.
 */

/**
 * Normalize a BCP-47 / i18n language tag (e.g. `"en-US"`, `"sv-SE"`,
 * `"fr"`) down to the base language for TTS voice selection. No allowlist —
 * the OS decides whether it actually has a voice for that language; if not,
 * `pickVoice` falls through to its language-agnostic fallbacks.
 */
export function ttsLanguageFor(uiLang: string | undefined | null): string {
    if (!uiLang) return 'en';
    const base = String(uiLang).split('-')[0].toLowerCase();
    return base || 'en';
}

// ---------------------------------------------------------------------------
// Voice profiles
// ---------------------------------------------------------------------------

export type VoiceGender = 'female' | 'male' | 'any';

/**
 * Per-character voice settings. Attach to an `AvatarChatConfig` (or to
 * interaction-box data from Kit) so the same speaker sounds consistent across
 * UI languages without forcing every locale to use, say, an English voice.
 */
export interface AvatarVoiceProfile {
    /** Preferred gender of the synthesised voice. `'any'` disables the bias. */
    gender?: VoiceGender;
    /** Utterance rate (0.1 – 10, default 1.0). */
    rate?: number;
    /** Utterance pitch (0 – 2, default 1.0). */
    pitch?: number;
    /**
     * Optional regex matched against `voice.name` to bias selection toward a
     * specific named voice family (e.g. branded characters). When supplied,
     * matches are preferred over the generic gender hints.
     */
    voiceNameHints?: RegExp;
}

/**
 * Default profile for female-presenting characters (e.g. Red). Mildly slower
 * + slightly higher pitch matches what NpcBubble / AvatarChat used previously.
 */
export const FEMALE_VOICE_PROFILE: AvatarVoiceProfile = {
    gender: 'female',
    rate: 0.92,
    pitch: 1.06,
};

/** Default profile for male-presenting characters. */
export const MALE_VOICE_PROFILE: AvatarVoiceProfile = {
    gender: 'male',
    rate: 0.95,
    pitch: 0.92,
};

/**
 * Profile to use when no character is associated with the spoken text (e.g.
 * generic interaction-box "Listen" buttons). No gender bias; default rate +
 * pitch so the OS default voice reads the text naturally.
 */
export const NEUTRAL_VOICE_PROFILE: AvatarVoiceProfile = {
    gender: 'any',
};

// Common name hints used when the OS doesn't expose a gender field on voices.
// Curated from Apple, Microsoft, Google and eSpeak voice rosters across en/sv
// (and a few en-localised aliases of fr/es voices that show up on Windows).
const FEMALE_NAME_HINTS =
    /female|woman|zira|samantha|karen|moira|fiona|serena|martha|victoria|amy|joanna|ivy|kimberly|linda|susan|hazel|sonia|mathilde|ines|celine|alva|jenny|aria|libby|sonia|nora/i;

const MALE_NAME_HINTS =
    /\bmale\b|man\b|alex|daniel|david|fred|mark|tom|oliver|ralph|thomas|lukas|oskar|jorge|bruno|claude|hugo|henrik|bengt|mattias|guy|ryan|brian|jason|christopher|eric/i;

function genderHintsFor(gender: VoiceGender | undefined): RegExp | null {
    if (gender === 'female') return FEMALE_NAME_HINTS;
    if (gender === 'male') return MALE_NAME_HINTS;
    return null;
}

/**
 * Pick the best available SpeechSynthesis voice for `(uiLang, profile)`.
 *
 * Priority:
 *   1. profile.voiceNameHints in the target language (branded character).
 *   2. gender-hint name match in the target language.
 *   3. literal "female" / "male" label match in the target language.
 *   4. any voice in the target language.
 *   5. gender-hint name match in any language (last-resort character match).
 *   6. browser default voice / first voice / null.
 */
export function pickVoice(
    uiLang: string | undefined | null,
    profile: AvatarVoiceProfile = NEUTRAL_VOICE_PROFILE,
): SpeechSynthesisVoice | null {
    if (typeof window === 'undefined' || !window.speechSynthesis) return null;
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return null;

    const targetLang = ttsLanguageFor(uiLang ?? 'en');
    const langMatch = (v: SpeechSynthesisVoice) =>
        v.lang.toLowerCase().startsWith(targetLang);

    if (profile.voiceNameHints) {
        const branded = voices.find(
            (v) => langMatch(v) && profile.voiceNameHints!.test(v.name),
        );
        if (branded) return branded;
    }

    const hints = genderHintsFor(profile.gender);
    if (hints) {
        const inLangByName = voices.find((v) => langMatch(v) && hints.test(v.name));
        if (inLangByName) return inLangByName;

        const labelRe = profile.gender === 'male' ? /\bmale\b|man\b/i : /female|woman/i;
        const inLangByLabel = voices.find((v) => langMatch(v) && labelRe.test(v.name));
        if (inLangByLabel) return inLangByLabel;
    }

    // Preference > nothing: fall back to any voice in the requested language.
    const anyInLang = voices.find(langMatch);
    if (anyInLang) return anyInLang;

    if (hints) {
        const anyByName = voices.find((v) => hints.test(v.name));
        if (anyByName) return anyByName;
    }

    return voices.find((v) => v.default) ?? voices[0] ?? null;
}

// ---------------------------------------------------------------------------
// parseVoiceProfile — single source of truth for turning Kit-side voice
// descriptors into an AvatarVoiceProfile. Used by every overlay that needs to
// honour `voice` (or `voiceProfile`) data shipped from `interactions.json`.
// ---------------------------------------------------------------------------

/**
 * Coerce a Kit-side voice descriptor into an {@link AvatarVoiceProfile}.
 *
 * Accepted shapes (all data lives in `interactions.json` on the Kit side; the
 * frontend never picks a default character — it only knows how to render the
 * data Kit gives it):
 *
 *   - **string** — `"female"` | `"male"` | `"any"` for the common case.
 *   - **object** — `{ gender?, rate?, pitch?, voiceNameHints? }` for full
 *     control. `voiceNameHints` may be a string regex source.
 *
 * Returns `undefined` when the payload doesn't define a voice. Callers should
 * treat that as "no preference" and let `speakText` fall back to
 * {@link NEUTRAL_VOICE_PROFILE}.
 */
export function parseVoiceProfile(raw: unknown): AvatarVoiceProfile | undefined {
    if (!raw) return undefined;

    if (typeof raw === 'string') {
        const gender = raw.toLowerCase() as VoiceGender;
        if (gender === 'female') return FEMALE_VOICE_PROFILE;
        if (gender === 'male') return MALE_VOICE_PROFILE;
        if (gender === 'any') return NEUTRAL_VOICE_PROFILE;
        return undefined;
    }

    if (typeof raw === 'object') {
        const obj = raw as Record<string, unknown>;
        const gender = (typeof obj.gender === 'string' ? obj.gender.toLowerCase() : 'any') as VoiceGender;
        const base =
            gender === 'female' ? FEMALE_VOICE_PROFILE :
            gender === 'male' ? MALE_VOICE_PROFILE :
            NEUTRAL_VOICE_PROFILE;
        const profile: AvatarVoiceProfile = { ...base };
        if (typeof obj.rate === 'number') profile.rate = obj.rate;
        if (typeof obj.pitch === 'number') profile.pitch = obj.pitch;
        if (typeof obj.voiceNameHints === 'string') {
            try {
                profile.voiceNameHints = new RegExp(obj.voiceNameHints, 'i');
            } catch {
                /* invalid regex from data — ignore, keep gender hints */
            }
        }
        return profile;
    }

    return undefined;
}

// ---------------------------------------------------------------------------
// speakText
// ---------------------------------------------------------------------------

export interface SpeechController {
    /** Cancels any in-flight utterance and resets state. */
    cancel: () => void;
}

/**
 * Speak `text` once. Cancels any in-flight utterance first and emits onStart /
 * onEnd / onError callbacks so the caller can drive its `aria-pressed` state.
 *
 * `voiceProfile` controls the speaker character (gender / rate / pitch /
 * optional name hint). Defaults to {@link NEUTRAL_VOICE_PROFILE}, matching the
 * behaviour expected for unattributed "Listen" buttons. `options.rate` and
 * `options.pitch` (when provided) win over the profile so callers can do
 * one-off overrides.
 *
 * Returns a controller exposing `cancel()` so the same caller can stop speech
 * (e.g. when toggling the speaker button off).
 */
export function speakText(
    text: string,
    options: {
        uiLang?: string | null;
        voiceProfile?: AvatarVoiceProfile;
        rate?: number;
        pitch?: number;
        onStart?: () => void;
        onEnd?: () => void;
        onError?: () => void;
    } = {},
): SpeechController {
    const noop: SpeechController = { cancel: () => {} };
    if (typeof window === 'undefined' || !window.speechSynthesis) return noop;
    const synth = window.speechSynthesis;
    const plain = String(text || '').replace(/\s*\n+\s*/g, ' ').trim();
    if (!plain) return noop;

    const profile = options.voiceProfile ?? NEUTRAL_VOICE_PROFILE;

    try {
        synth.cancel();
        synth.resume();
        const voice = pickVoice(options.uiLang, profile);
        const utter = new SpeechSynthesisUtterance(plain);
        utter.rate = options.rate ?? profile.rate ?? 1;
        utter.pitch = options.pitch ?? profile.pitch ?? 1;
        if (voice) utter.voice = voice;
        utter.lang = voice?.lang ?? ttsLanguageFor(options.uiLang ?? 'en');
        let started = false;
        const fireStart = () => {
            if (started) return;
            started = true;
            options.onStart?.();
        };
        utter.onstart = fireStart;
        utter.onend = () => options.onEnd?.();
        utter.onerror = () => options.onError?.();
        synth.speak(utter);
        // Browsers vary on whether `onstart` fires reliably (esp. Safari);
        // optimistically signal so the caller's `aria-pressed` is in sync.
        fireStart();
    } catch {
        options.onError?.();
        return noop;
    }

    return {
        cancel: () => {
            try { synth.cancel(); } catch { /* ignore */ }
        },
    };
}
