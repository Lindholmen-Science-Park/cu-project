import React from 'react';
import micSvg from '@icons/chat/Microphone.svg';
import './MicButton.css';

export type MicButtonProps = Omit<React.ComponentPropsWithoutRef<'button'>, 'type' | 'children' | 'aria-pressed'> & {
    /** Reflects listening / recording for toggles (maps to `aria-pressed`). */
    pressed?: boolean;
};

/**
 * Shared voice-input control: one SVG, one size, one chrome across the app.
 * Dark-theme overrides live in {@link ../../features/streaming/DarkMode.css}.
 */
export const MicButton = React.forwardRef<HTMLButtonElement, MicButtonProps>(function MicButton(
    { pressed, className, disabled, ...rest },
    ref,
) {
    return (
        <button
            ref={ref}
            type="button"
            className={['mic-button', className].filter(Boolean).join(' ')}
            disabled={disabled}
            aria-pressed={pressed === undefined ? undefined : pressed}
            {...rest}
        >
            <img
                className="mic-button__icon"
                src={micSvg}
                alt=""
                width={20}
                height={20}
                draggable={false}
            />
        </button>
    );
});
