import { useNavigation, useAppUI } from '../contexts';

/**
 * True when the CU "Find my seat" bottom sheet is the foreground surface
 * (including when opened from Search while Controls menu stays visible).
 */
export function useSeatSheetForeground(): boolean {
    const nav = useNavigation();
    const appUI = useAppUI();
    return (
        (nav.seatWidgetOpen || appUI.seatPanelStickyOpen) &&
        !appUI.seatArrivalCelebrationVisible &&
        !appUI.poiArrivalVisible &&
        !nav.restroomWidgetOpen &&
        !nav.quietZoneWidgetOpen &&
        !appUI.seatStreamOverlayActive
    );
}
