import seatHierarchy from './data/seat_hierarchy.json';

/**
 * Cascading section -> row -> seat tree consumed by the CU seat-finder
 * dropdowns. Generated offline by
 * `kit-app-template-main/source/data/Assets/Seats/Tools/build_seat_hierarchy.py`
 * from `extracted_seats_with_rows.json` -- re-run that script (or the full
 * `rebuild_seats.py` pipeline) whenever the source DXF changes so the
 * dropdowns stay aligned with the runtime `seats_lookup.json`.
 *
 * Wheelchair uses the same nested shape as walking (ticket row + seat number,
 * e.g. row ``6`` and seats ``1``…``n`` matching ids like ``C-6-1``).
 */
export interface SeatHierarchy {
    /** section -> row -> ordered seat numbers. */
    walking: Record<string, Record<string, string[]>>;
    /** section -> row -> ordered wheelchair seat numbers. */
    wheelchair: Record<string, Record<string, string[]>>;
}

export const SEAT_HIERARCHY = seatHierarchy as SeatHierarchy;

/**
 * Stadium section codes for the CU walking-mode seat finder.
 *
 * Sourced from the generated hierarchy so the dropdown only ever offers
 * sections that actually contain navigable seats (currently 19 of A-Z).
 */
export const CU_STADIUM_SECTION_LETTERS: readonly string[] = Object.freeze(
    Object.keys(SEAT_HIERARCHY.walking).sort(),
);

/**
 * Sections that contain wheelchair seats (`tier: "wheelchair"` in
 * `extracted_seats_with_rows.json`).
 */
export const CU_WHEELCHAIR_SECTION_LETTERS: readonly string[] = Object.freeze(
    Object.keys(SEAT_HIERARCHY.wheelchair).sort(),
);

/** Rows available for `section` in walking mode (numeric ascending). */
export const getWalkingRowsForSection = (section: string): readonly string[] => {
    const rows = SEAT_HIERARCHY.walking[section.toUpperCase()];
    return rows ? Object.keys(rows) : [];
};

/** Seats available for `section` + `row` in walking mode. */
export const getWalkingSeatsForRow = (section: string, row: string): readonly string[] => {
    return SEAT_HIERARCHY.walking[section.toUpperCase()]?.[row] ?? [];
};

/** Wheelchair rows for `section` (e.g. ticket row ``6``). */
export const getWheelchairRowsForSection = (section: string): readonly string[] => {
    const rows = SEAT_HIERARCHY.wheelchair[section.toUpperCase()];
    return rows ? Object.keys(rows) : [];
};

/** Wheelchair seats for `section` + `row`. */
export const getWheelchairSeatsForRow = (section: string, row: string): readonly string[] => {
    return SEAT_HIERARCHY.wheelchair[section.toUpperCase()]?.[row] ?? [];
};
