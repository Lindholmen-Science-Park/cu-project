/**
 * Localized POI titles from structured metadata (restroom flags, POI type).
 * English `display_name` in JSON remains a CAD/source label; the UI uses i18n.
 */

export type PoiTitleTranslate = (key: string, options?: Record<string, unknown>) => string;

function resolveRestroomTitle(md: Record<string, unknown>, t: PoiTitleTranslate): string {
    const forMen = md.for_men === true;
    const forWomen = md.for_women === true;
    const isUnisex = md.is_unisex === true;
    const isAccessible = md.is_accessible === true;
    const seats = typeof md.toilet_seats === 'number' ? md.toilet_seats : 0;
    const fallback = typeof md.display_name === 'string' ? md.display_name : '';

    if (!forMen && forWomen && !isUnisex) {
        return t('search.poiNameRestroomWomen');
    }
    if (forMen && !forWomen && !isUnisex) {
        return t('search.poiNameRestroomMen');
    }

    if (isAccessible && forMen && forWomen) {
        if (isUnisex) {
            return seats > 1 ? t('search.poiNameRestroomAccessiblePlural') : t('search.poiNameRestroomAccessibleSingular');
        }
        return t('search.poiNameRestroomAccessibleSingular');
    }

    if (isUnisex && forMen && forWomen && !isAccessible) {
        return t('search.poiNameRestroomUnisex');
    }

    return fallback;
}

/**
 * Returns a non-empty localized title when the POI type has structured labels;
 * otherwise returns `metadata.display_name` (quiet venues, odd cases) or ''.
 */
export function resolvePoiLocalizedTitle(
    poiType: string,
    metadata: Record<string, unknown> | null | undefined,
    t: PoiTitleTranslate,
): string {
    const md = metadata || {};

    switch (poiType) {
        case 'restroom':
            return resolveRestroomTitle(md, t);
        case 'exit':
            return t('search.poiNameEmergencyExit');
        case 'kiosk':
            return t('search.poiNameKiosk');
        case 'elevator':
            return t('search.poiNameElevator');
        case 'ticket_office':
            return t('search.poiNameTicketOffice');
        case 'quiet_zone':
            return typeof md.display_name === 'string' ? md.display_name : '';
        default:
            return typeof md.display_name === 'string' ? md.display_name : '';
    }
}
