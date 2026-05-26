import React from 'react';
import './MediaPlayerControls.css';

/**
 * Shared media-player chrome — used by every overlay that plays time-based media:
 *   - `VideoBookPlayer` (chaptered MP4)
 *   - `Video360Overlay`  (equirectangular 360° MP4 on a Three.js sphere)
 *   - `SpatialSoundOverlay` (FOA / stereo audio with optional captions)
 *
 * Before this module lived here each player had its own copy of these four buttons
 * (settings cog, mute toggle, captions toggle, play/pause) with subtly drifting
 * dimensions / hover states / active-state colours. Centralising them keeps the
 * three immersive surfaces visually locked together: a Figma tweak to "the mute
 * button" now travels via one CSS file, and the active-state contract
 * (Dark-Purple glyph on a white pill) is impossible to re-derive incorrectly per
 * overlay.
 *
 * Layout/positioning stays with the host overlay — these components ship size +
 * colour + glyph only. Pinning to the left/right of a transport row, fading with
 * the chrome's auto-hide, etc. is done with extra classes on the parent. That
 * way the buttons stay layout-agnostic and we don't have to fork them when a new
 * player picks a different bar geometry.
 *
 * All four buttons accept a `className` so callers can layer in those layout
 * concerns (`.vbp-transport .mpc-btn--mute { position: absolute; left: 0 }` etc.)
 * without forking the component.
 */

interface BaseButtonProps {
    onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
    /** Extra classes for layout / positioning (e.g. `position: absolute; left: 0`). */
    className?: string;
    ariaLabel: string;
    title?: string;
    disabled?: boolean;
}

function joinClasses(...parts: Array<string | false | null | undefined>): string {
    return parts.filter(Boolean).join(' ');
}

/* ------------------------------------------------------------------ */
/*  Settings button — opens the shared `VideoBookSettingsPanel`        */
/* ------------------------------------------------------------------ */

/**
 * Sliders / equaliser glyph. Same path data as the videobook's
 * `VbpPeopleGroupsIcon` (`cu-icon-btn-svg`) so re-using `.cu-icon-btn`'s 23×23 box
 * makes it pixel-aligned in either container.
 */
const MediaSettingsIcon: React.FC = () => (
    <svg
        xmlns="http://www.w3.org/2000/svg"
        width="23"
        height="23"
        viewBox="0 0 23 23"
        fill="none"
        className="mpc-settings-icon"
        aria-hidden
    >
        <path
            d="M2.875 7.18769C2.875 6.99706 2.95073 6.81424 3.08552 6.67944C3.22032 6.54465 3.40314 6.46892 3.59377 6.46892H6.93334C7.08826 5.94995 7.40654 5.49483 7.84085 5.17124C8.27515 4.84764 8.8023 4.67285 9.3439 4.67285C9.8855 4.67285 10.4126 4.84764 10.847 5.17124C11.2813 5.49483 11.5995 5.94995 11.7545 6.46892H19.4066C19.5973 6.46892 19.7801 6.54465 19.9149 6.67944C20.0497 6.81424 20.1254 6.99706 20.1254 7.18769C20.1254 7.37832 20.0497 7.56114 19.9149 7.69593C19.7801 7.83073 19.5973 7.90645 19.4066 7.90645H11.7545C11.5995 8.42543 11.2813 8.88054 10.847 9.20414C10.4126 9.52773 9.8855 9.70252 9.3439 9.70252C8.8023 9.70252 8.27515 9.52773 7.84085 9.20414C7.40654 8.88054 7.08826 8.42543 6.93334 7.90645H3.59377C3.40314 7.90645 3.22032 7.83073 3.08552 7.69593C2.95073 7.56114 2.875 7.37832 2.875 7.18769ZM19.4066 15.0941H17.5046C17.3497 14.5751 17.0314 14.12 16.5971 13.7964C16.1628 13.4728 15.6356 13.2981 15.094 13.2981C14.5524 13.2981 14.0253 13.4728 13.591 13.7964C13.1567 14.12 12.8384 14.5751 12.6835 15.0941H3.59377C3.40314 15.0941 3.22032 15.1698 3.08552 15.3046C2.95073 15.4394 2.875 15.6223 2.875 15.8129C2.875 16.0035 2.95073 16.1863 3.08552 16.3211C3.22032 16.4559 3.40314 16.5317 3.59377 16.5317H12.6835C12.8384 17.0506 13.1567 17.5057 13.591 17.8293C14.0253 18.1529 14.5524 18.3277 15.094 18.3277C15.6356 18.3277 16.1628 18.1529 16.5971 17.8293C17.0314 17.5057 17.3497 17.0506 17.5046 16.5317H19.4066C19.5973 16.5317 19.7801 16.4559 19.9149 16.3211C20.0497 16.1863 20.1254 16.0035 20.1254 15.8129C20.1254 15.6223 20.0497 15.4394 19.9149 15.3046C19.7801 15.1698 19.5973 15.0941 19.4066 15.0941Z"
            fill="currentColor"
        />
    </svg>
);

export const MediaSettingsButton: React.FC<BaseButtonProps> = ({
    onClick,
    className,
    ariaLabel,
    title,
    disabled,
}) => (
    <button
        type="button"
        className={joinClasses('mpc-btn', 'mpc-btn--settings', className)}
        onClick={onClick}
        aria-label={ariaLabel}
        title={title ?? ariaLabel}
        disabled={disabled}
    >
        <MediaSettingsIcon />
    </button>
);

/* ------------------------------------------------------------------ */
/*  Mute toggle                                                        */
/* ------------------------------------------------------------------ */

export const MediaVolumeOnIcon: React.FC<{ className?: string }> = ({ className }) => (
    <svg
        className={className}
        width="20"
        height="20"
        viewBox="0 0 19 17"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
    >
        <path
            d="M11.25 0.643462V15.5997C11.2519 15.7116 11.2248 15.8221 11.1712 15.9205C11.1177 16.0188 11.0396 16.1015 10.9445 16.1607C10.8365 16.2249 10.7116 16.2551 10.5862 16.2473C10.4608 16.2395 10.3406 16.194 10.2414 16.1169L5.11875 12.1325C5.08161 12.1032 5.05162 12.0658 5.03105 12.0231C5.01048 11.9805 4.99986 11.9338 5 11.8864V4.36143C5.00014 4.3139 5.01112 4.26703 5.0321 4.22439C5.05309 4.18175 5.08352 4.14445 5.12109 4.11534L10.2437 0.130962C10.356 0.0439698 10.4946 -0.00219208 10.6366 8.00398e-05C10.7786 0.00235216 10.9156 0.0529228 11.025 0.143462C11.0969 0.205207 11.1543 0.282004 11.1932 0.368411C11.2321 0.454818 11.2515 0.54872 11.25 0.643462ZM3.4375 4.37393H1.25C0.918479 4.37393 0.600537 4.50563 0.366116 4.74005C0.131696 4.97447 0 5.29241 0 5.62393V10.6239C0 10.9555 0.131696 11.2734 0.366116 11.5078C0.600537 11.7422 0.918479 11.8739 1.25 11.8739H3.4375C3.52038 11.8739 3.59987 11.841 3.65847 11.7824C3.71708 11.7238 3.75 11.6443 3.75 11.5614V4.68643C3.75 4.60355 3.71708 4.52407 3.65847 4.46546C3.59987 4.40686 3.52038 4.37393 3.4375 4.37393ZM13.3414 6.00206C13.2797 6.05629 13.2293 6.12216 13.193 6.1959C13.1568 6.26964 13.1355 6.3498 13.1302 6.4318C13.125 6.51379 13.136 6.59602 13.1626 6.67376C13.1892 6.7515 13.2308 6.82324 13.2852 6.88487C13.5866 7.22724 13.7529 7.66776 13.7529 8.12393C13.7529 8.5801 13.5866 9.02062 13.2852 9.36299C13.2294 9.42431 13.1863 9.49611 13.1585 9.57422C13.1307 9.65234 13.1188 9.73519 13.1233 9.81797C13.1279 9.90075 13.1489 9.9818 13.185 10.0564C13.2212 10.131 13.2719 10.1976 13.3341 10.2525C13.3962 10.3073 13.4687 10.3492 13.5473 10.3758C13.6258 10.4023 13.7088 10.413 13.7915 10.4071C13.8742 10.4012 13.9549 10.379 14.029 10.3417C14.103 10.3043 14.1688 10.2526 14.2227 10.1896C14.7254 9.61887 15.0027 8.88445 15.0027 8.12393C15.0027 7.36341 14.7254 6.62899 14.2227 6.05831C14.1684 5.99647 14.1025 5.94596 14.0287 5.90965C13.9549 5.87335 13.8746 5.85197 13.7925 5.84674C13.7104 5.84152 13.6281 5.85255 13.5503 5.8792C13.4725 5.90585 13.4007 5.9476 13.3391 6.00206H13.3414ZM16.5359 3.95753C16.4822 3.89325 16.416 3.84044 16.3414 3.80225C16.2668 3.76405 16.1853 3.74126 16.1017 3.73521C16.0181 3.72916 15.9341 3.73999 15.8548 3.76704C15.7755 3.7941 15.7024 3.83683 15.6399 3.8927C15.5775 3.94857 15.5269 4.01643 15.4912 4.09225C15.4555 4.16807 15.4354 4.2503 15.4321 4.33404C15.4288 4.41779 15.4424 4.50134 15.472 4.57973C15.5017 4.65812 15.5468 4.72974 15.6047 4.79034C16.4248 5.70707 16.8781 6.89392 16.8781 8.12393C16.8781 9.35394 16.4248 10.5408 15.6047 11.4575C15.5468 11.5181 15.5017 11.5897 15.472 11.6681C15.4424 11.7465 15.4288 11.8301 15.4321 11.9138C15.4354 11.9976 15.4555 12.0798 15.4912 12.1556C15.5269 12.2314 15.5775 12.2993 15.6399 12.3552C15.7024 12.411 15.7755 12.4538 15.8548 12.4808C15.9341 12.5079 16.0181 12.5187 16.1017 12.5127C16.1853 12.5066 16.2668 12.4838 16.3414 12.4456C16.416 12.4074 16.4822 12.3546 16.5359 12.2903C17.5607 11.1445 18.1272 9.66117 18.1272 8.12393C18.1272 6.58669 17.5607 5.10337 16.5359 3.95753Z"
            fill="currentColor"
        />
    </svg>
);

export const MediaMuteIcon: React.FC<{ className?: string }> = ({ className }) => (
    <svg
        className={className}
        width="20"
        height="20"
        viewBox="0 0 19 17"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
    >
        <path
            d="M15.4625 14.5786C15.5189 14.6392 15.5626 14.7103 15.5913 14.7879C15.62 14.8654 15.6329 14.9479 15.6295 15.0306C15.626 15.1132 15.6062 15.1943 15.5712 15.2692C15.5361 15.3442 15.4866 15.4114 15.4254 15.467C15.3642 15.5226 15.2925 15.5656 15.2146 15.5933C15.1367 15.621 15.0541 15.633 14.9715 15.6286C14.8889 15.6241 14.808 15.6033 14.7335 15.5674C14.659 15.5315 14.5924 15.4811 14.5375 15.4192L11.25 11.8028V15.5997C11.2519 15.7116 11.2248 15.8221 11.1712 15.9205C11.1177 16.0188 11.0396 16.1015 10.9445 16.1607C10.8365 16.2249 10.7116 16.2551 10.5862 16.2473C10.4608 16.2395 10.3406 16.194 10.2414 16.1169L5.12031 12.1325C5.08309 12.1035 5.05293 12.0664 5.0321 12.0241C5.01126 11.9817 5.00029 11.9352 5 11.888V4.92784L2.0375 1.66924C1.98115 1.60871 1.93737 1.53759 1.9087 1.46001C1.88004 1.38243 1.86705 1.29993 1.8705 1.2173C1.87396 1.13466 1.89378 1.05353 1.92881 0.978614C1.96385 0.903696 2.01341 0.836476 2.07462 0.780852C2.13582 0.725228 2.20746 0.682305 2.28538 0.654571C2.3633 0.626838 2.44595 0.614845 2.52854 0.619288C2.61112 0.623731 2.69201 0.644521 2.7665 0.680455C2.84099 0.716388 2.90761 0.766748 2.9625 0.828618L15.4625 14.5786ZM13.3367 10.2458C13.4609 10.3555 13.6237 10.4113 13.7891 10.4011C13.9545 10.3908 14.109 10.3153 14.2188 10.1911C14.7215 9.62044 14.9988 8.88601 14.9988 8.12549C14.9988 7.36497 14.7215 6.63055 14.2188 6.05987C14.1655 5.9952 14.0997 5.94192 14.0254 5.90318C13.9511 5.86444 13.8697 5.84104 13.7862 5.83437C13.7027 5.8277 13.6186 5.8379 13.5391 5.86436C13.4596 5.89081 13.3862 5.93299 13.3233 5.98838C13.2605 6.04377 13.2094 6.11124 13.1731 6.18678C13.1368 6.26232 13.1161 6.34439 13.1121 6.4281C13.1082 6.5118 13.1212 6.59545 13.1502 6.67405C13.1793 6.75266 13.2238 6.82462 13.2812 6.88565C13.5827 7.22802 13.749 7.66854 13.749 8.12471C13.749 8.58088 13.5827 9.02141 13.2812 9.36378C13.1717 9.4881 13.1159 9.65087 13.1263 9.81628C13.1367 9.98168 13.2124 10.1362 13.3367 10.2458ZM16.5336 3.95753C16.4798 3.89325 16.4137 3.84044 16.3391 3.80225C16.2645 3.76405 16.1829 3.74126 16.0993 3.73521C16.0157 3.72916 15.9318 3.73999 15.8525 3.76704C15.7731 3.7941 15.7001 3.83683 15.6376 3.8927C15.5751 3.94857 15.5245 4.01643 15.4888 4.09225C15.4531 4.16807 15.433 4.2503 15.4297 4.33404C15.4264 4.41779 15.44 4.50134 15.4697 4.57973C15.4993 4.65812 15.5444 4.72974 15.6023 4.79034C16.4224 5.70707 16.8758 6.89392 16.8758 8.12393C16.8758 9.35394 16.4224 10.5408 15.6023 11.4575C15.5444 11.5181 15.4993 11.5897 15.4697 11.6681C15.44 11.7465 15.4264 11.8301 15.4297 11.9138C15.433 11.9976 15.4531 12.0798 15.4888 12.1556C15.5245 12.2314 15.5751 12.2993 15.6376 12.3552C15.7001 12.411 15.7731 12.4538 15.8525 12.4808C15.9318 12.5079 16.0157 12.5187 16.0993 12.5127C16.1829 12.5066 16.2645 12.4838 16.3391 12.4456C16.4137 12.4074 16.4798 12.3546 16.5336 12.2903C17.5584 11.1445 18.1249 9.66117 18.1249 8.12393C18.1249 6.58669 17.5584 5.10337 16.5336 3.95753ZM10.7031 7.48878C10.7453 7.53666 10.8012 7.57047 10.8632 7.58565C10.9252 7.60083 10.9904 7.59665 11.05 7.57367C11.1096 7.5507 11.1607 7.51003 11.1964 7.45714C11.2322 7.40425 11.2509 7.34167 11.25 7.27784V0.643462C11.2515 0.54872 11.2321 0.454818 11.1932 0.368411C11.1543 0.282004 11.0969 0.205207 11.025 0.143462C10.9156 0.0529228 10.7786 0.00235216 10.6366 8.00398e-05C10.4946 -0.00219208 10.356 0.0439698 10.2437 0.130962L6.86172 2.75909C6.82773 2.78555 6.79958 2.81874 6.77903 2.8566C6.75848 2.89446 6.74598 2.93615 6.74231 2.97907C6.73865 3.02198 6.74389 3.06519 6.75772 3.10599C6.77154 3.14678 6.79365 3.18428 6.82266 3.21612L10.7031 7.48878ZM3.4375 4.37393H1.25C0.918479 4.37393 0.600537 4.50563 0.366116 4.74005C0.131696 4.97447 0 5.29241 0 5.62393V10.6239C0 10.9555 0.131696 11.2734 0.366116 11.5078C0.600537 11.7422 0.918479 11.8739 1.25 11.8739H3.4375C3.52038 11.8739 3.59987 11.841 3.65847 11.7824C3.71708 11.7238 3.75 11.6443 3.75 11.5614V4.68643C3.75 4.60355 3.71708 4.52407 3.65847 4.46546C3.59987 4.40686 3.52038 4.37393 3.4375 4.37393Z"
            fill="currentColor"
        />
    </svg>
);

interface MuteButtonProps extends BaseButtonProps {
    /** True when audio is currently muted (drives the active visual + glyph swap). */
    muted: boolean;
}

export const MediaMuteButton: React.FC<MuteButtonProps> = ({
    muted,
    onClick,
    className,
    ariaLabel,
    title,
    disabled,
}) => (
    <button
        type="button"
        className={joinClasses(
            'mpc-btn',
            'mpc-btn--mute',
            muted && 'mpc-btn--active',
            className,
        )}
        onClick={onClick}
        aria-label={ariaLabel}
        aria-pressed={muted}
        title={title ?? ariaLabel}
        disabled={disabled}
    >
        {muted ? <MediaMuteIcon /> : <MediaVolumeOnIcon />}
    </button>
);

/* ------------------------------------------------------------------ */
/*  Captions toggle                                                    */
/* ------------------------------------------------------------------ */

interface CaptionsButtonProps extends BaseButtonProps {
    /** True when captions are currently being rendered. */
    captionsOn: boolean;
    /**
     * False when the current source has no captions track. Defaults to `true`.
     * Buttons in the false state apply `.mpc-btn--disabled` (lower opacity, no
     * pointer-events) so the affordance reads as "not available" rather than "off".
     */
    hasCaptions?: boolean;
}

export const MediaCaptionsButton: React.FC<CaptionsButtonProps> = ({
    captionsOn,
    hasCaptions = true,
    onClick,
    className,
    ariaLabel,
    title,
    disabled,
}) => (
    <button
        type="button"
        className={joinClasses(
            'mpc-btn',
            'mpc-btn--cc',
            captionsOn && hasCaptions && 'mpc-btn--active',
            !hasCaptions && 'mpc-btn--disabled',
            className,
        )}
        onClick={hasCaptions ? onClick : undefined}
        aria-label={ariaLabel}
        aria-pressed={hasCaptions ? captionsOn : undefined}
        title={title ?? ariaLabel}
        disabled={disabled || !hasCaptions}
    >
        <span className="mpc-cc-icon" aria-hidden />
    </button>
);

/* ------------------------------------------------------------------ */
/*  Play / pause (large white circle)                                  */
/* ------------------------------------------------------------------ */

interface PlayPauseButtonProps extends BaseButtonProps {
    /** True when the underlying media is currently advancing. */
    isPlaying: boolean;
}

export const MediaPlayPauseButton: React.FC<PlayPauseButtonProps> = ({
    isPlaying,
    onClick,
    className,
    ariaLabel,
    title,
    disabled,
}) => (
    <button
        type="button"
        className={joinClasses('mpc-btn', 'mpc-btn--play', className)}
        onClick={onClick}
        aria-label={ariaLabel}
        title={title ?? ariaLabel}
        disabled={disabled}
    >
        {isPlaying ? (
            <svg
                xmlns="http://www.w3.org/2000/svg"
                width="22"
                height="24"
                viewBox="0 0 22 24"
                fill="none"
                aria-hidden
            >
                <path
                    d="M22 2V22C22 22.5304 21.7893 23.0391 21.4142 23.4142C21.0391 23.7893 20.5304 24 20 24H15C14.4696 24 13.9609 23.7893 13.5858 23.4142C13.2107 23.0391 13 22.5304 13 22V2C13 1.46957 13.2107 0.960859 13.5858 0.585786C13.9609 0.210714 14.4696 0 15 0H20C20.5304 0 21.0391 0.210714 21.4142 0.585786C21.7893 0.960859 22 1.46957 22 2ZM7 0H2C1.46957 0 0.960859 0.210714 0.585786 0.585786C0.210714 0.960859 0 1.46957 0 2V22C0 22.5304 0.210714 23.0391 0.585786 23.4142C0.960859 23.7893 1.46957 24 2 24H7C7.53043 24 8.03914 23.7893 8.41421 23.4142C8.78929 23.0391 9 22.5304 9 22V2C9 1.46957 8.78929 0.960859 8.41421 0.585786C8.03914 0.210714 7.53043 0 7 0Z"
                    fill="currentColor"
                />
            </svg>
        ) : (
            <svg viewBox="0 0 24 24" width="30" height="30" fill="none" aria-hidden>
                <polygon points="6,3 20,12 6,21" fill="currentColor" />
            </svg>
        )}
    </button>
);
