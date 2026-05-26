import React, { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import PanelCloseButton from '../controls/PanelCloseButton';
import { useVideoBookSettings } from '../../streaming/contexts';
import { useModalAccessibility } from '../../streaming/hooks/useModalAccessibility';
import {
    CAPTION_SIZE_STEPS,
    PLAYBACK_SPEED_STEPS,
    type CaptionSizeIndex,
    type PlaybackSpeedIndex,
} from './videoBookSettings';
import { stopRangeSliderKeyPropagation } from '../../streaming/utils/immersiveMediaKeyboard';
import './VideoBookSettingsPanel.css';

/**
 * Shared media player settings panel — used by the videobook (`VideoBookOverlay`),
 * the 360° video overlay (`Video360Overlay`), and the spatial sound overlay
 * (`SpatialSoundOverlay`). Every control is bound to `VideoBookSettingsContext` so
 * the choices survive view transitions, panel re-mounts, and even player close/reopen
 * within the same browser session (refreshing the page resets to the defaults — no
 * localStorage involved).
 *
 * Cards per Figma:
 *   1. Captions font size — Aa↔Aa range slider, bound to `captionSizeIndex`. Each player
 *      reflects the value via a `data-caption-size` attribute on its caption strip.
 *      **Always rendered** — captions exist on every surface that uses this panel.
 *   2. Playback autoplay  — ON/OFF PillSwitch bound to `autoplayEnabled`; flips the
 *      videobook's "play continuously through every chapter" mode mid-playback.
 *      **Hidden when `showAutoplay={false}`** — 360° videos and spatial sound have no
 *      chapters so the concept doesn't apply.
 *   3. Playback speed     — slow↔fast range slider bound to `playbackSpeedIndex`; each
 *      player applies it to `HTMLMediaElement.playbackRate`.
 *      **Hidden when `showPlaybackSpeed={false}`** — spatial sound is non-time-scrubbed
 *      audio where rate-changing isn't a designed-for affordance.
 *
 * Renders as a top-aligned modal floating over the host overlay. Backdrop click and
 * Escape key both dismiss.
 */
export interface VideoBookSettingsPanelProps {
    onClose: () => void;
    /**
     * Whether to render the "Playback autoplay" card. Defaults to `true` (videobook
     * usage). Set `false` for surfaces that don't have chapter boundaries to play
     * continuously through (360° video, spatial sound).
     */
    showAutoplay?: boolean;
    /**
     * Whether to render the "Playback speed" card. Defaults to `true`. Set `false` for
     * the spatial sound overlay where playback-rate isn't an exposed control.
     */
    showPlaybackSpeed?: boolean;
    /**
     * i18n key for the panel header title. Defaults to the videobook label
     * (`'videobook.videoSettings.title'`); 360° video and spatial sound pass
     * their own keys so the header reads "360° Video settings" /
     * "Spatial sound settings" instead of "Video Book settings".
     */
    titleKey?: string;
}

/**
 * Range slider wrapped with purple dots that mark the discrete stop positions (per Figma).
 * `tickCount` controls how many dots are rendered along the track:
 *   - 2 → dots at the min/max endpoints only ("from / to" feel; used by playback-speed)
 *   - 3 → dots at min, midpoint, and max (used by captions size: small / default / large)
 * Each dot lines up with where the thumb rests at that stop, so the thumb passes over them.
 */
function RangeWithDots(
    props: React.InputHTMLAttributes<HTMLInputElement> & { ariaLabel: string; tickCount?: 2 | 3 },
) {
    const { ariaLabel, className, tickCount = 2, onKeyDown, ...rest } = props;
    return (
        <span className="vbsp-range-wrap">
            <span className="vbsp-range-dot vbsp-range-dot--start" aria-hidden />
            {tickCount === 3 && (
                <span className="vbsp-range-dot vbsp-range-dot--middle" aria-hidden />
            )}
            <input
                {...rest}
                type="range"
                tabIndex={0}
                className={`vbsp-range${className ? ` ${className}` : ''}`}
                aria-label={ariaLabel}
                onKeyDown={(e) => {
                    stopRangeSliderKeyPropagation(e);
                    onKeyDown?.(e);
                }}
            />
            <span className="vbsp-range-dot vbsp-range-dot--end" aria-hidden />
        </span>
    );
}

/**
 * Slow / "min" glyph for the playback-speed slider's left edge. Uses `currentColor` so
 * the path inherits the slider row's text colour (Dark Purple). Original SVG asset lives
 * at `@icons/media/videobook/videobook-speed-min.svg` for reference / future re-use.
 */
function SpeedMinIcon() {
    return (
        <svg
            className="vbsp-speed-icon vbsp-speed-icon--slow"
            width="28"
            height="14"
            viewBox="0 0 28 14"
            fill="none"
            aria-hidden
        >
            <path
                d="M10.0605 5.27952C8.98698 5.27952 7.97152 5.07754 7.01416 4.67356C6.0568 4.26406 5.20182 3.64703 4.44922 2.82249C4.96387 2.16396 5.50342 1.62718 6.06787 1.21214C6.63786 0.797099 7.25212 0.48997 7.91064 0.290752C8.57471 0.0915329 9.31348 -0.00530951 10.127 0.000224345C10.9349 0.000224345 11.6654 0.0998337 12.3184 0.299052C12.9714 0.492737 13.5745 0.794332 14.1279 1.20384C14.6868 1.61334 15.2236 2.13353 15.7383 2.76438C14.9857 3.6 14.1335 4.22809 13.1816 4.64866C12.2298 5.06923 11.1895 5.27952 10.0605 5.27952ZM4.59863 10.6667C4.2832 10.5561 3.95671 10.4647 3.61914 10.3928C3.28711 10.3153 2.91357 10.2766 2.49854 10.2766H1.54395C1.05143 10.2766 0.669596 10.1991 0.398438 10.0442C0.132812 9.88922 0 9.66787 0 9.38011C0 9.18089 0.0442708 9.00934 0.132812 8.86546C0.221354 8.71604 0.348633 8.5611 0.514648 8.40061C0.691732 8.22353 0.896484 8.02155 1.12891 7.79466C1.36133 7.56224 1.60482 7.28001 1.85938 6.94798C2.11393 6.61595 2.36296 6.21198 2.60645 5.73606C2.78906 5.37636 2.97445 5.03603 3.1626 4.71507C3.35628 4.38857 3.54997 4.08144 3.74365 3.79368C4.19743 4.26959 4.72314 4.69293 5.3208 5.0637C5.92399 5.43447 6.51888 5.725 7.10547 5.93528C7.0446 6.4776 6.90072 7.04205 6.67383 7.62864C6.44694 8.2097 6.15365 8.76585 5.79395 9.2971C5.43978 9.82835 5.04134 10.2849 4.59863 10.6667ZM10.0771 12.5261C9.45182 12.5261 8.88184 12.4431 8.36719 12.2771C7.85254 12.1111 7.38216 11.9174 6.95605 11.696C6.52995 11.4747 6.13151 11.2893 5.76074 11.1399C6.22559 10.7138 6.62679 10.2323 6.96436 9.69554C7.30745 9.15322 7.57861 8.58877 7.77783 8.00218C7.98258 7.41559 8.10986 6.83177 8.15967 6.25071C8.46956 6.32819 8.78499 6.38629 9.10596 6.42503C9.42692 6.46377 9.75342 6.48037 10.0854 6.47483C10.7495 6.47483 11.4053 6.39459 12.0527 6.23411C12.0915 6.84283 12.2132 7.44326 12.418 8.03538C12.6227 8.62197 12.8994 9.17812 13.248 9.70384C13.5967 10.2296 14.009 10.6972 14.4849 11.1067C14.1086 11.2893 13.7018 11.4913 13.2646 11.7126C12.8275 11.934 12.3433 12.1249 11.812 12.2854C11.2863 12.4459 10.708 12.5261 10.0771 12.5261ZM15.5391 10.6252C15.0798 10.2102 14.6785 9.74257 14.3354 9.22239C13.9979 8.70221 13.724 8.15713 13.5137 7.58714C13.3034 7.01715 13.1733 6.45546 13.1235 5.90208C13.4777 5.76927 13.8485 5.59218 14.2358 5.37083C14.6232 5.14394 15.0023 4.88938 15.373 4.60716C15.7493 4.3194 16.0924 4.01504 16.4023 3.69407C16.5739 3.96523 16.7676 4.3111 16.9834 4.73167C17.1992 5.14671 17.4233 5.59772 17.6558 6.0847C17.8882 6.57168 18.1178 7.06142 18.3447 7.55394C18.5771 8.04091 18.7957 8.48916 19.0005 8.89866C19.2052 9.30817 19.3823 9.6402 19.5317 9.89476C19.3657 9.99436 19.1333 10.0718 18.8345 10.1272C18.5356 10.177 18.223 10.2047 17.8965 10.2102C17.4538 10.2379 17.0387 10.2904 16.6514 10.3679C16.2695 10.4398 15.8988 10.5256 15.5391 10.6252ZM2.34912 13.8625C1.76253 13.8625 1.27555 13.7436 0.888184 13.5056C0.506348 13.2676 0.31543 12.9328 0.31543 12.5012C0.31543 12.1802 0.437174 11.9367 0.680664 11.7707C0.929688 11.6047 1.20638 11.4913 1.51074 11.4304C1.7653 11.3695 2.00326 11.3225 2.22461 11.2893C2.4515 11.2561 2.67562 11.2063 2.89697 11.1399C3.42822 11.2284 3.97054 11.3917 4.52393 11.6296C5.07731 11.8731 5.59473 12.1332 6.07617 12.4099C5.68327 12.8471 5.14648 13.1985 4.46582 13.4641C3.79069 13.7297 3.08512 13.8625 2.34912 13.8625ZM17.855 13.8791C17.368 13.8791 16.881 13.8183 16.394 13.6965C15.9126 13.5748 15.4671 13.4005 15.0576 13.1736C14.6536 12.9522 14.3244 12.6894 14.0698 12.385C14.3631 12.2079 14.6924 12.0308 15.0576 11.8537C15.4284 11.6822 15.8047 11.5328 16.1865 11.4055C16.5739 11.2782 16.9419 11.1897 17.2905 11.1399C17.5285 11.1675 17.7443 11.1897 17.938 11.2063C18.1372 11.2229 18.353 11.2395 18.5854 11.2561C18.8123 11.2893 19.0282 11.3612 19.2329 11.4719C19.4377 11.577 19.6037 11.7154 19.731 11.8869C19.8582 12.064 19.9219 12.2715 19.9219 12.5095C19.9219 12.9467 19.7254 13.2842 19.3325 13.5222C18.9452 13.7602 18.4526 13.8791 17.855 13.8791ZM20.4531 9.54612C20.182 9.00934 19.908 8.46425 19.6313 7.91087C19.3602 7.35195 19.1222 6.88157 18.9175 6.49974C19.0835 6.37799 19.244 6.23688 19.3989 6.0764C19.5594 5.91038 19.7061 5.70009 19.8389 5.44554C19.9772 5.19098 20.1017 4.87002 20.2124 4.48265C20.3784 3.85732 20.6274 3.30947 20.9595 2.83909C21.297 2.36318 21.7148 1.99518 22.2129 1.73509C22.7165 1.475 23.3031 1.34495 23.9727 1.34495C24.7474 1.34495 25.4253 1.5497 26.0063 1.95921C26.5929 2.36871 27.0467 2.94147 27.3677 3.67747C27.6886 4.40794 27.8491 5.26015 27.8491 6.23411C27.8491 6.66022 27.6969 7.03099 27.3926 7.34642C27.0882 7.65631 26.6566 7.89703 26.0977 8.06858C25.5443 8.24013 24.8885 8.32591 24.1304 8.32591C23.6047 8.32591 23.1426 8.38955 22.7441 8.51683C22.3457 8.6441 21.9666 8.80459 21.6069 8.99827C21.2528 9.18642 20.8682 9.36904 20.4531 9.54612ZM24.1802 5.44554C24.3905 5.44554 24.5731 5.36806 24.728 5.21311C24.8885 5.05817 24.9688 4.86725 24.9688 4.64036C24.9688 4.42454 24.8885 4.23916 24.728 4.08421C24.5731 3.92373 24.3905 3.84349 24.1802 3.84349C23.9533 3.84349 23.7624 3.92373 23.6074 4.08421C23.4525 4.23916 23.375 4.42454 23.375 4.64036C23.375 4.86725 23.4525 5.05817 23.6074 5.21311C23.7624 5.36806 23.9533 5.44554 24.1802 5.44554Z"
                fill="currentColor"
            />
        </svg>
    );
}

/** Fast / "max" glyph for the playback-speed slider's right edge. */
function SpeedMaxIcon() {
    return (
        <svg
            className="vbsp-speed-icon vbsp-speed-icon--fast"
            width="26"
            height="19"
            viewBox="0 0 26 19"
            fill="none"
            aria-hidden
        >
            <path
                d="M13.3975 17.606C13.0654 17.606 12.7334 17.5506 12.4014 17.4399C12.0693 17.3293 11.693 17.0885 11.2725 16.7178L7.86084 13.8623C7.7889 13.8623 7.71696 13.8651 7.64502 13.8706C7.57308 13.8706 7.50391 13.8706 7.4375 13.8706C6.60742 13.8706 5.84375 13.7848 5.14648 13.6133C4.45475 13.4362 3.82943 13.154 3.27051 12.7666C2.71712 12.3792 2.23568 11.8646 1.82617 11.2227C1.29492 11.2282 0.857747 11.0926 0.514648 10.8159C0.171549 10.5337 0 10.1574 0 9.68701C0 9.26091 0.149414 8.91781 0.448242 8.65771C0.752604 8.39209 1.13167 8.26481 1.58545 8.27588C1.96175 7.19124 2.4515 6.29476 3.05469 5.58643C3.65788 4.87809 4.34961 4.35238 5.12988 4.00928C5.91569 3.66064 6.76514 3.48633 7.67822 3.48633C8.37549 3.48633 9.02572 3.56657 9.62891 3.72705C10.2321 3.882 10.8132 4.09782 11.3721 4.37451C11.9365 4.64567 12.5093 4.95833 13.0903 5.3125C13.6769 5.66667 14.2995 6.04297 14.958 6.44141C15.4284 6.70703 15.8545 6.93945 16.2363 7.13867C16.6237 7.33789 16.9889 7.4375 17.332 7.4375C17.57 7.4375 17.7747 7.39046 17.9463 7.29639C18.1234 7.19678 18.3032 7.06396 18.4858 6.89795L13.7876 3.90967C13.439 3.68831 13.0765 3.44482 12.7002 3.1792C12.3294 2.90804 12.014 2.64242 11.7539 2.38232C11.4993 2.1167 11.3721 1.87598 11.3721 1.66016C11.3721 1.41667 11.48 1.19531 11.6958 0.996094C11.9116 0.791341 12.1883 0.614258 12.5259 0.464844C12.8634 0.309896 13.2148 0.193685 13.5801 0.116211C13.9508 0.038737 14.2884 0 14.5928 0C15.3509 0 16.1035 0.196452 16.8506 0.589355C17.5977 0.982259 18.27 1.59928 18.8677 2.44043L20.9429 5.37061C21.6401 5.354 22.271 5.46468 22.8354 5.70264C23.3999 5.94059 23.8869 6.27816 24.2964 6.71533C24.7059 7.15251 25.0213 7.66162 25.2427 8.24268C25.464 8.82373 25.5747 9.44352 25.5747 10.1021C25.5747 10.8381 25.4557 11.4108 25.2178 11.8203C24.9854 12.2243 24.634 12.5093 24.1636 12.6753C23.6987 12.8358 23.1204 12.916 22.4287 12.916C21.9528 12.916 21.5156 12.8634 21.1172 12.7583C20.7188 12.6532 20.3452 12.512 19.9966 12.335C19.6479 12.1579 19.3159 11.9642 19.0005 11.7539C18.6408 11.9255 18.3115 12.0942 18.0127 12.2603C17.7194 12.4263 17.4399 12.5895 17.1743 12.75C16.9364 12.7057 16.6984 12.6753 16.4604 12.6587C16.2225 12.6366 15.979 12.6255 15.73 12.6255C15.4256 12.6255 15.1213 12.6393 14.8169 12.667C14.5181 12.6947 14.2303 12.7362 13.9536 12.7915L13.3892 11.4883C12.7915 10.1104 12.0057 9.08382 11.0317 8.40869C10.0578 7.73356 8.93717 7.396 7.66992 7.396C7.26595 7.396 6.90348 7.4458 6.58252 7.54541C6.26709 7.64502 6.10938 7.84147 6.10938 8.13477C6.10938 8.31738 6.16748 8.45296 6.28369 8.5415C6.3999 8.63005 6.55208 8.67432 6.74023 8.67432H7.74463C8.40869 8.67432 9.02572 8.79883 9.5957 9.04785C10.1712 9.29688 10.6859 9.65934 11.1396 10.1353C11.5934 10.6112 11.9753 11.1867 12.2852 11.8618L13.2314 13.9536C13.4805 13.9038 13.7184 13.854 13.9453 13.8042C14.1777 13.7489 14.4406 13.7046 14.7339 13.6714C15.0272 13.6326 15.3869 13.6133 15.813 13.6133C16.6597 13.6133 17.3818 13.7267 17.9795 13.9536C18.5771 14.1805 19.0337 14.4904 19.3491 14.8833C19.6646 15.2707 19.8223 15.7051 19.8223 16.1865C19.8223 16.6348 19.6562 16.9834 19.3242 17.2324C18.9922 17.4814 18.519 17.606 17.9048 17.606C17.6281 17.606 17.3901 17.5811 17.1909 17.5312C16.9917 17.4814 16.7759 17.4344 16.5435 17.3901C16.311 17.3459 16.0094 17.3237 15.6387 17.3237C15.0964 17.3237 14.6592 17.3708 14.3271 17.4648C14.0007 17.5589 13.6908 17.606 13.3975 17.606ZM7.06396 18.2783C6.17855 18.2783 5.47021 18.1095 4.93896 17.772C4.41325 17.4399 4.15039 16.9972 4.15039 16.4438C4.15039 16.0731 4.2832 15.777 4.54883 15.5557C4.81999 15.3288 5.18522 15.2153 5.64453 15.2153C5.88249 15.2153 6.11491 15.2264 6.3418 15.2485C6.56869 15.2651 6.7762 15.2845 6.96436 15.3066C7.15804 15.3288 7.32129 15.3398 7.4541 15.3398C7.53711 15.3398 7.61182 15.3371 7.67822 15.3315C7.74463 15.326 7.80827 15.3205 7.86914 15.3149L10.4092 17.4565C10.0052 17.7222 9.54036 17.9242 9.01465 18.0625C8.48893 18.2064 7.8387 18.2783 7.06396 18.2783ZM21.939 9.77832C22.1548 9.77832 22.3374 9.69808 22.4868 9.5376C22.6418 9.37158 22.7192 9.18066 22.7192 8.96484C22.7192 8.75456 22.6445 8.57471 22.4951 8.42529C22.3457 8.27588 22.1631 8.20117 21.9473 8.20117C21.737 8.20117 21.5544 8.28141 21.3994 8.44189C21.25 8.60238 21.1753 8.78776 21.1753 8.99805C21.1753 9.20833 21.25 9.39095 21.3994 9.5459C21.5488 9.70085 21.7287 9.77832 21.939 9.77832Z"
                fill="currentColor"
            />
        </svg>
    );
}

/**
 * iOS-style ON/OFF switch composed of an external uppercase text label sitting next to a
 * 45×24 pill with a sliding 18×18 knob (per Figma "Toggle container 69×24, gap 4").
 * The text label is decorative — the underlying button carries the accessible state
 * (`role=switch`, `aria-checked`) so screen-reader users get a single semantic control.
 */
function PillSwitch({
    checked,
    onChange,
    label,
}: {
    checked: boolean;
    onChange: (next: boolean) => void;
    label: string;
}) {
    const { t } = useTranslation();
    return (
        <span className="vbsp-toggle">
            <span className="vbsp-toggle__text" aria-hidden>
                {checked ? t('common.on') : t('common.off')}
            </span>
            <button
                type="button"
                role="switch"
                aria-checked={checked}
                aria-label={label}
                className={`vbsp-toggle__pill${checked ? ' vbsp-toggle__pill--on' : ''}`}
                onClick={() => onChange(!checked)}
            >
                <span className="vbsp-toggle__knob" aria-hidden />
            </button>
        </span>
    );
}

const VideoBookSettingsPanel: React.FC<VideoBookSettingsPanelProps> = ({
    onClose,
    showAutoplay = true,
    showPlaybackSpeed = true,
    titleKey = 'videobook.videoSettings.title',
}) => {
    const { t } = useTranslation();
    const {
        captionSizeIndex,
        setCaptionSizeIndex,
        autoplayEnabled,
        setAutoplayEnabled,
        playbackSpeedIndex,
        setPlaybackSpeedIndex,
    } = useVideoBookSettings();

    const captionStep = CAPTION_SIZE_STEPS[captionSizeIndex] ?? CAPTION_SIZE_STEPS[1];
    const speedStep = PLAYBACK_SPEED_STEPS[playbackSpeedIndex] ?? PLAYBACK_SPEED_STEPS[1];

    const panelRef = useRef<HTMLDivElement>(null);
    useModalAccessibility(panelRef);

    const handleBackdropClick = useCallback(() => {
        onClose();
    }, [onClose]);

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                onClose();
            }
        };
        window.addEventListener('keydown', onKey, true);
        return () => window.removeEventListener('keydown', onKey, true);
    }, [onClose]);

    return (
        <div className="vbsp-overlay" onClick={handleBackdropClick}>
            <div
                ref={panelRef}
                className="vbsp-panel"
                role="dialog"
                aria-modal="true"
                aria-labelledby="vbsp-title"
                onClick={(e) => e.stopPropagation()}
            >
                <header className="vbsp-header">
                    <h2 id="vbsp-title" className="vbsp-title">
                        {t(titleKey)}
                    </h2>
                    <PanelCloseButton
                        className="vbp-close-btn vbsp-close"
                        onClick={(e) => {
                            e.stopPropagation();
                            onClose();
                        }}
                        ariaLabel={t('common.close')}
                        title={t('common.close')}
                    />
                </header>

                {/* Card 1 — Captions font size (3 discrete steps: small / default / large;
                    only the endpoint dots are drawn — the slider still snaps to the middle). */}
                <section className="vbsp-card vbsp-card--captions">
                    <h3 className="vbsp-card-title">{t('videobook.videoSettings.captionFontSize')}</h3>
                    <div className="vbsp-slider-row">
                        <span className="vbsp-aa vbsp-aa--sm" aria-hidden>Aa</span>
                        <RangeWithDots
                            min={0}
                            max={CAPTION_SIZE_STEPS.length - 1}
                            step={1}
                            value={captionSizeIndex}
                            onChange={(e) =>
                                setCaptionSizeIndex(Number(e.target.value) as CaptionSizeIndex)
                            }
                            ariaLabel={t('videobook.videoSettings.captionFontSizeAria', {
                                step: t(captionStep.labelKey),
                                pct: captionStep.pct,
                            })}
                            aria-valuemin={0}
                            aria-valuemax={CAPTION_SIZE_STEPS.length - 1}
                            aria-valuenow={captionSizeIndex}
                            aria-valuetext={t(captionStep.labelKey)}
                        />
                        <span className="vbsp-aa vbsp-aa--lg" aria-hidden>Aa</span>
                    </div>
                </section>

                {/* Card 2 — Playback autoplay (videobook-only; 360° videos have no chapters) */}
                {showAutoplay && (
                    <section className="vbsp-card vbsp-card--autoplay">
                        <header className="vbsp-card-header">
                            <h3 className="vbsp-card-title">
                                {t('videobook.videoSettings.playbackAutoplay')}
                            </h3>
                            <PillSwitch
                                checked={autoplayEnabled}
                                onChange={setAutoplayEnabled}
                                label={t('videobook.videoSettings.playbackAutoplay')}
                            />
                        </header>
                        <p className="vbsp-card-hint">{t('videobook.videoSettings.playbackAutoplayHint')}</p>
                    </section>
                )}

                {/* Card 3 — Playback speed (3 discrete steps, mirrors the captions card).
                    Hidden for spatial sound where rate-changing isn't an exposed affordance. */}
                {showPlaybackSpeed && (
                    <section className="vbsp-card vbsp-card--speed">
                        <h3 className="vbsp-card-title">{t('videobook.videoSettings.playbackSpeed')}</h3>
                        <div className="vbsp-slider-row">
                            <SpeedMinIcon />
                            <RangeWithDots
                                min={0}
                                max={PLAYBACK_SPEED_STEPS.length - 1}
                                step={1}
                                value={playbackSpeedIndex}
                                onChange={(e) =>
                                    setPlaybackSpeedIndex(Number(e.target.value) as PlaybackSpeedIndex)
                                }
                                ariaLabel={t('videobook.videoSettings.playbackSpeedAria', {
                                    step: t(speedStep.labelKey),
                                    speed: speedStep.rate.toFixed(2),
                                })}
                                aria-valuemin={0}
                                aria-valuemax={PLAYBACK_SPEED_STEPS.length - 1}
                                aria-valuenow={playbackSpeedIndex}
                                aria-valuetext={t(speedStep.labelKey)}
                            />
                            <SpeedMaxIcon />
                        </div>
                    </section>
                )}
            </div>
        </div>
    );
};

export default VideoBookSettingsPanel;
