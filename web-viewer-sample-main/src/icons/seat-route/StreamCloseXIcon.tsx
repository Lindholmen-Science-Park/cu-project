import React from 'react';

/** Same X mark as `PanelCloseButton` (CU panels). */
const StreamCloseXIcon: React.FC<{ className?: string }> = ({ className }) => (
    <svg
        className={className}
        width="23"
        height="23"
        viewBox="0 0 23 23"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
    >
        <path
            d="M18.478 17.461a1.016 1.016 0 0 1-1.017 1.017 1.016 1.016 0 0 1-.718-.298L11.5 12.517l-5.96 5.96a1.016 1.016 0 0 1-1.436-1.435L10.484 11.5 4.523 5.54a1.016 1.016 0 0 1 1.436-1.436L11.5 10.484l5.96-5.96a1.016 1.016 0 0 1 1.436 1.435L12.517 11.5l5.96 5.961c.188.188.293.443.293.709a1.01 1.01 0 0 1-.293.709Z"
            fill="currentColor"
        />
    </svg>
);

export default StreamCloseXIcon;
