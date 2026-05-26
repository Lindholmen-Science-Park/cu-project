import React from 'react';

interface NavArrivalCheckIconProps {
    className?: string;
}

/** Rounded-square checkmark — destination reached (Figma arrival state). */
const NavArrivalCheckIcon: React.FC<NavArrivalCheckIconProps> = ({ className }) => (
    <svg
        className={['cu-seat-panel__status-flag', className].filter(Boolean).join(' ')}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden={true}
    >
        <path
            d="M18.0001 3.59998C19.3238 3.59998 20.4001 4.67623 20.4001 5.99998V18C20.4001 19.3237 19.3238 20.4 18.0001 20.4H6.0001C4.67635 20.4 3.6001 19.3237 3.6001 18V5.99998C3.6001 4.67623 4.67635 3.59998 6.0001 3.59998H18.0001ZM16.4251 7.86373C16.0238 7.57123 15.4613 7.66123 15.1688 8.06248L10.6913 14.22L8.7376 12.2662C8.3851 11.9137 7.8151 11.9137 7.46635 12.2662C7.1176 12.6187 7.11385 13.1887 7.46635 13.5375L10.1663 16.2375C10.3538 16.425 10.6126 16.5187 10.8713 16.5C11.1301 16.4812 11.3738 16.3462 11.5276 16.1325L16.6238 9.11998C16.9163 8.71873 16.8263 8.15623 16.4251 7.86373Z"
            fill="#351A84"
        />
    </svg>
);

export default NavArrivalCheckIcon;
