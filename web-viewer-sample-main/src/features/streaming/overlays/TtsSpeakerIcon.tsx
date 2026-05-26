import React from 'react';

/**
 * Shared "play text-to-speech" glyph (Figma `Group 181`): a speaker silhouette
 * with three left-aligned wave bars indicating spoken-word output.
 *
 * Used by every TTS / "Listen" button in the overlays — NPC bubbles,
 * interaction box bubbles, and avatar chat — so they share one canonical
 * design. The glyph is rendered with `currentColor`, so the host button
 * controls the colour via its own `color` rule (Dark-Purple inactive,
 * Off-white when the bubble is in its "playing/active" state).
 *
 * NOTE: this icon is intentionally distinct from the audio mute/unmute glyph
 * used in the media-player and app-settings buttons — those still use the
 * classic speaker icon. Do not consolidate the two.
 */
export type TtsSpeakerIconProps = {
    className?: string;
    /** Visual size in CSS pixels — defaults to 14 to match historical sizing. */
    size?: number;
};

const TtsSpeakerIcon: React.FC<TtsSpeakerIconProps> = ({ className, size = 14 }) => {
    return (
        <svg
            className={className}
            width={size}
            height={size}
            viewBox="0 0 16 13"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            preserveAspectRatio="xMidYMid meet"
            aria-hidden
            focusable="false"
        >
            <path
                d="M12.7301 3.53316V12.2515C12.7301 12.3195 12.711 12.386 12.6749 12.4437C12.6389 12.5013 12.5875 12.5477 12.5264 12.5776C12.4653 12.6074 12.3971 12.6195 12.3295 12.6125C12.2619 12.6055 12.1976 12.5797 12.1439 12.538L8.97264 10.0719H6.91793C6.72525 10.0719 6.54045 9.99535 6.4042 9.8591C6.26795 9.72285 6.19141 9.53806 6.19141 9.34537V6.43926C6.19141 6.24658 6.26795 6.06178 6.4042 5.92553C6.54045 5.78928 6.72525 5.71274 6.91793 5.71274H8.97264L12.1439 3.24663C12.1976 3.20491 12.2619 3.17909 12.3295 3.17209C12.3971 3.1651 12.4653 3.17722 12.5264 3.20706C12.5875 3.23691 12.6389 3.2833 12.6749 3.34094C12.711 3.39859 12.7301 3.46518 12.7301 3.53316ZM14.1832 6.43926C14.0868 6.43926 13.9944 6.47754 13.9263 6.54566C13.8582 6.61379 13.8199 6.70618 13.8199 6.80253V8.98211C13.8199 9.07845 13.8582 9.17085 13.9263 9.23898C13.9944 9.3071 14.0868 9.34537 14.1832 9.34537C14.2795 9.34537 14.3719 9.3071 14.4401 9.23898C14.5082 9.17085 14.5464 9.07845 14.5464 8.98211V6.80253C14.5464 6.70618 14.5082 6.61379 14.4401 6.54566C14.3719 6.47754 14.2795 6.43926 14.1832 6.43926ZM15.6362 5.71274C15.5399 5.71274 15.4475 5.75101 15.3794 5.81914C15.3112 5.88726 15.273 5.97966 15.273 6.076V9.70864C15.273 9.80498 15.3112 9.89738 15.3794 9.9655C15.4475 10.0336 15.5399 10.0719 15.6362 10.0719C15.7326 10.0719 15.825 10.0336 15.8931 9.9655C15.9612 9.89738 15.9995 9.80498 15.9995 9.70864V6.076C15.9995 5.97966 15.9612 5.88726 15.8931 5.81914C15.825 5.75101 15.7326 5.71274 15.6362 5.71274Z"
                fill="currentColor"
            />
            <rect width="11.6244" height="1.05677" rx="0.528383" fill="currentColor" />
            <rect y="3.17017" width="7.39735" height="1.05677" rx="0.528383" fill="currentColor" />
            <rect y="6.34058" width="4.22706" height="1.05677" rx="0.528383" fill="currentColor" />
        </svg>
    );
};

export default TtsSpeakerIcon;
