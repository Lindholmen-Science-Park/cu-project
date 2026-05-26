import { useEffect, useState } from 'react';

export interface VisualViewportInsets {
    top: number;
    left: number;
    width: number;
    height: number;
    /** True when the visible viewport is much shorter than the layout viewport (mobile keyboard). */
    keyboardLikelyOpen: boolean;
}

function readInsets(): VisualViewportInsets {
    if (typeof window === 'undefined') {
        return { top: 0, left: 0, width: 0, height: 0, keyboardLikelyOpen: false };
    }
    const vv = window.visualViewport;
    if (!vv) {
        return {
            top: 0,
            left: 0,
            width: window.innerWidth,
            height: window.innerHeight,
            keyboardLikelyOpen: false,
        };
    }
    const innerH = window.innerHeight;
    return {
        top: vv.offsetTop,
        left: vv.offsetLeft,
        width: vv.width,
        height: vv.height,
        keyboardLikelyOpen: vv.height < innerH * 0.85,
    };
}

/**
 * Tracks `window.visualViewport` so fixed overlays can shrink above the mobile
 * software keyboard instead of staying full layout-viewport height.
 */
export function useVisualViewportInsets(): VisualViewportInsets {
    const [insets, setInsets] = useState(readInsets);

    useEffect(() => {
        const vv = window.visualViewport;
        if (!vv) return;

        const sync = () => setInsets(readInsets());
        sync();
        vv.addEventListener('resize', sync);
        vv.addEventListener('scroll', sync);
        window.addEventListener('resize', sync);
        window.addEventListener('orientationchange', sync);
        return () => {
            vv.removeEventListener('resize', sync);
            vv.removeEventListener('scroll', sync);
            window.removeEventListener('resize', sync);
            window.removeEventListener('orientationchange', sync);
        };
    }, []);

    return insets;
}
