import type { TFunction } from 'i18next';

export type RouteErrorAnnouncement = {
    title: string;
    suggestion?: string;
};

/** Localized status for Kit `navmeshRouteError` (WCAG 4.1.3). */
export function buildNavRouteErrorAnnouncement(
    routeId: string,
    _kitError?: string,
    t: TFunction = ((key: string) => key) as TFunction,
): RouteErrorAnnouncement | null {
    switch (routeId) {
        case 'poi_nav':
        case 'exit_nav':
            return {
                title: t('search.poiRouteUnreachable'),
                suggestion: t('search.poiRouteErrorSuggestion'),
            };
        case 'quiet_zone_nav':
            return {
                title: t('search.quietRouteUnreachable'),
                suggestion: t('search.poiRouteErrorSuggestion'),
            };
        case 'bird_eye':
            return {
                title: t('search.directionsRouteFailed'),
                suggestion: t('search.directionsRouteErrorSuggestion'),
            };
        case 'seat_nav':
            return {
                title: t('search.directionsRouteFailed'),
                suggestion: t('seat.errorSuggestionUnreachable'),
            };
        default:
            return null;
    }
}
