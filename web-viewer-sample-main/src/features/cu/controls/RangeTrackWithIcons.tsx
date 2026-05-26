import React from 'react';
import type { SettingsEndIconSpec } from './settings-icons/SettingsIcons';

interface RangeTrackWithIconsProps {
    railClassName: string;
    startIconClassName: string;
    endIconClassName: string;
    trackWrapClassName: string;
    trackClassName: string;
    trackSrc: string;
    startIcon: SettingsEndIconSpec;
    endIcon: SettingsEndIconSpec;
    trackWidth?: number;
    trackHeight?: number;
    /** When set, wraps the track + this node in a column (tick labels use full track width). */
    belowTrack?: React.ReactNode;
    trackColumnClassName?: string;
    children: React.ReactNode;
}

const RangeTrackWithIcons: React.FC<RangeTrackWithIconsProps> = ({
    railClassName,
    startIconClassName,
    endIconClassName,
    trackWrapClassName,
    trackClassName,
    trackSrc,
    startIcon,
    endIcon,
    trackWidth = 230,
    trackHeight = 6,
    belowTrack,
    trackColumnClassName,
    children,
}) => {
    const trackBody = (
        <div className={trackWrapClassName}>
            <img
                className={trackClassName}
                src={trackSrc}
                alt=""
                width={trackWidth}
                height={trackHeight}
                draggable={false}
                aria-hidden
            />
            {children}
        </div>
    );

    const middle =
        belowTrack != null ? (
            <div className={trackColumnClassName}>
                {trackBody}
                {belowTrack}
            </div>
        ) : (
            trackBody
        );

    return (
        <div className={railClassName}>
            <img
                className={startIconClassName}
                src={startIcon.src}
                alt=""
                width={startIcon.width}
                height={startIcon.height}
                draggable={false}
                aria-hidden
            />
            {middle}
            <img
                className={endIconClassName}
                src={endIcon.src}
                alt=""
                width={endIcon.width}
                height={endIcon.height}
                draggable={false}
                aria-hidden
            />
        </div>
    );
};

export default RangeTrackWithIcons;
