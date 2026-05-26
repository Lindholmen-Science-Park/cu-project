import React from 'react';
import { useTranslation } from 'react-i18next';
import type { RouteMeasure } from '../../../types';
import {
    CU_STADIUM_SECTION_LETTERS,
    CU_WHEELCHAIR_SECTION_LETTERS,
} from '../constants';
import SignpostIcon from '@icons/seat-navigation/SignpostIcon';
import FlagPennantIcon from '@icons/seat-navigation/FlagPennantIcon';
import RouteMeasureDisplay from './RouteMeasureDisplay';
import SeatChoiceDropdown from './SeatChoiceDropdown';

interface SeatFormBodyProps {
    isCu: boolean;
    isWheelchair: boolean;
    section: string;
    row: string;
    seat: string;
    /**
     * Cascading option lists owned by `SeatNavigateWidget` (which knows about
     * the seat-hierarchy import). The form body is purely presentational and
     * never derives them itself.
     */
    availableRows: readonly string[];
    availableSeats: readonly string[];
    onSectionChange: (raw: string) => void;
    onRowChange: (raw: string) => void;
    onSeatChange: (raw: string) => void;
    onEnterSubmit: () => void;
    disabled: boolean;
    /** Kit could not navigate/teleport to the selected seat (not invalid dropdown input). */
    seatRouteError: boolean;
    seatStatusText: string;
    seatErrorSuggestion: string;
    activeSeatRouteId: string | null;
    hasValidRoute: boolean;
    isComplete: boolean;
    onGetDirectionsOrStop: () => void;
    onTeleport?: () => void;
    actionsBusy: boolean;
    routeMeasure?: RouteMeasure;
    hasMeasure: boolean;
    hideRouteMeasureInPanel: boolean;
    onRefreshRouteMeasure?: () => void;
    onArmCooldown: () => void;
}

const SeatFormBody: React.FC<SeatFormBodyProps> = ({
    isCu,
    isWheelchair,
    section,
    row,
    seat,
    availableRows,
    availableSeats,
    onSectionChange,
    onRowChange,
    onSeatChange,
    onEnterSubmit,
    disabled,
    seatRouteError,
    seatStatusText,
    seatErrorSuggestion,
    activeSeatRouteId,
    hasValidRoute,
    isComplete,
    onGetDirectionsOrStop,
    onTeleport,
    actionsBusy,
    routeMeasure,
    hasMeasure,
    hideRouteMeasureInPanel,
    onRefreshRouteMeasure,
    onArmCooldown,
}) => {
    const { t } = useTranslation();
    const bodyClass = isCu ? 'cu-seat-panel__body' : 'seat-panel-default__body';
    const fieldsRowClass = 'seat-panel-default__row';
    const fieldWrapClass = isCu ? 'cu-seat-panel__field' : 'seat-panel-default__field';

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') onEnterSubmit();
    };

    const sectionGlyph = section ? section.trim().toUpperCase() : '';
    const sectionList = isWheelchair
        ? CU_WHEELCHAIR_SECTION_LETTERS
        : CU_STADIUM_SECTION_LETTERS;
    /** Keep stale drafts visible in the trigger so the user can see what to clear. */
    const sectionValue = sectionGlyph && sectionList.includes(sectionGlyph) ? sectionGlyph : '';
    const showCuStatusAsTwoRows =
        isCu &&
        hasValidRoute &&
        !!sectionGlyph &&
        !!row.trim() &&
        !!seat.trim();

    const cuStatusTopRow = `${t('seat.section')} ${sectionGlyph}, ${t('seat.row')} ${row.trim()},`;
    const cuStatusBottomRow = `${t('seat.seatLabel')} ${seat.trim()}`;

    return (
        <div className={bodyClass}>
            {isCu ? (
                <div className="cu-seat-panel__fields">
                    <p id="cu-seat-form-hint" className="sr-only">
                        {t('seat.formInstructions')}
                    </p>
                    <div className="cu-seat-panel__field-row">
                        <label
                            id="cu-seat-section-label"
                            className="cu-seat-panel__field-label"
                            htmlFor="cu-seat-section"
                        >
                            {t('seat.section')}
                        </label>
                        <div className="cu-seat-panel__field-control">
                            <SeatChoiceDropdown
                                id="cu-seat-section"
                                labelId="cu-seat-section-label"
                                inputName="stadium-section"
                                autoComplete="off"
                                describedBy="cu-seat-form-hint"
                                value={sectionValue}
                                options={sectionList}
                                placeholder={t('seat.sectionSelectPlaceholder')}
                                ariaLabel={t('seat.section')}
                                onChange={onSectionChange}
                                onKeyDown={handleKeyDown}
                                disabled={disabled}
                            />
                        </div>
                    </div>
                    <div className="cu-seat-panel__field-row">
                        <label
                            id="cu-seat-row-label"
                            className="cu-seat-panel__field-label"
                            htmlFor="cu-seat-row"
                        >
                            {t('seat.row')}
                        </label>
                        <div className="cu-seat-panel__field-control">
                            <SeatChoiceDropdown
                                id="cu-seat-row"
                                labelId="cu-seat-row-label"
                                inputName="stadium-row"
                                autoComplete="off"
                                describedBy="cu-seat-form-hint"
                                value={row.trim()}
                                options={availableRows}
                                placeholder={t('seat.rowSelectPlaceholder')}
                                ariaLabel={t('seat.row')}
                                onChange={onRowChange}
                                onKeyDown={handleKeyDown}
                                disabled={disabled || availableRows.length === 0}
                            />
                        </div>
                    </div>
                    <div className="cu-seat-panel__field-row">
                        <label
                            id="cu-seat-number-label"
                            className="cu-seat-panel__field-label"
                            htmlFor="cu-seat-number"
                        >
                            {t('seat.seatLabel')}
                        </label>
                        <div className="cu-seat-panel__field-control">
                            <SeatChoiceDropdown
                                id="cu-seat-number"
                                labelId="cu-seat-number-label"
                                inputName="stadium-seat"
                                autoComplete="off"
                                describedBy="cu-seat-form-hint"
                                value={seat.trim()}
                                options={availableSeats}
                                placeholder={t('seat.seatSelectPlaceholder')}
                                ariaLabel={t('seat.seatLabel')}
                                onChange={onSeatChange}
                                onKeyDown={handleKeyDown}
                                disabled={disabled || availableSeats.length === 0}
                            />
                        </div>
                    </div>
                </div>
            ) : (
                <div className={fieldsRowClass}>
                    <div className={fieldWrapClass}>
                        <label className="seat-panel-default__field-label" htmlFor="cu-seat-section-default">
                            {t('seat.section')}
                        </label>
                        <input
                            type="text"
                            inputMode="text"
                            maxLength={1}
                            autoCapitalize="characters"
                            autoCorrect="off"
                            spellCheck={false}
                            autoComplete="off"
                            id="cu-seat-section-default"
                            name="stadium-section"
                            placeholder={t('seat.sectionPlaceholder')}
                            value={section}
                            onChange={(e) => onSectionChange(e.target.value)}
                            onKeyDown={handleKeyDown}
                            disabled={disabled}
                            className="seat-panel-default__input"
                        />
                    </div>
                    <div className={fieldWrapClass}>
                        <label className="seat-panel-default__field-label" htmlFor="cu-seat-row-default">
                            {t('seat.row')}
                        </label>
                        <input
                            type="text"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            id="cu-seat-row-default"
                            name="stadium-row"
                            autoComplete="off"
                            placeholder={t('seat.rowPlaceholder')}
                            value={row}
                            onChange={(e) => onRowChange(e.target.value.replace(/\D/g, ''))}
                            onKeyDown={handleKeyDown}
                            disabled={disabled}
                            className="seat-panel-default__input"
                        />
                    </div>
                    <div className={fieldWrapClass}>
                        <label className="seat-panel-default__field-label" htmlFor="cu-seat-number-default">
                            {t('seat.seatLabel')}
                        </label>
                        <input
                            type="text"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            id="cu-seat-number-default"
                            name="stadium-seat"
                            autoComplete="off"
                            placeholder={
                                isWheelchair ? t('seat.seatPlaceholderWheelchair') : t('seat.seatPlaceholder')
                            }
                            value={seat}
                            onChange={(e) => onSeatChange(e.target.value.replace(/\D/g, ''))}
                            onKeyDown={handleKeyDown}
                            disabled={disabled}
                            className="seat-panel-default__input"
                        />
                    </div>
                </div>
            )}

            {isCu && seatRouteError && (
                <div
                    id="cu-seat-form-error"
                    className="cu-seat-panel__status cu-seat-panel__status--error cu-seat-panel__status--inline"
                    role="alert"
                    aria-live="assertive"
                >
                    <FlagPennantIcon aria-hidden />
                    <span className="cu-seat-panel__status-text">
                        <span className="cu-seat-panel__status-line">{seatStatusText}</span>
                        {seatErrorSuggestion ? (
                            <span className="cu-seat-panel__status-line cu-seat-panel__status-suggestion">
                                {seatErrorSuggestion}
                            </span>
                        ) : null}
                    </span>
                </div>
            )}

            <div className={isCu ? 'cu-seat-panel__btn-row' : 'seat-panel-default__btn-row'}>
                <button
                    type="button"
                    onClick={onGetDirectionsOrStop}
                    disabled={(!hasValidRoute && !isComplete) || actionsBusy}
                    className={
                        isCu
                            ? `cu-seat-panel__btn ${hasValidRoute ? 'cu-seat-panel__btn--stop' : 'cu-seat-panel__btn--primary'}`
                            : `seat-panel-default__btn ${hasValidRoute ? 'seat-panel-default__btn--stop' : 'seat-panel-default__btn--go'}`
                    }
                >
                    {isCu && !hasValidRoute ? <SignpostIcon /> : null}
                    <span className={isCu ? 'cu-seat-panel__btn-label' : undefined}>
                        {hasValidRoute ? t('common.stop') : t('seat.getDirections')}
                    </span>
                </button>
                {onTeleport && (
                    <button
                        type="button"
                        onClick={onTeleport}
                        disabled={!isComplete || actionsBusy}
                        className={isCu ? 'cu-seat-panel__btn cu-seat-panel__btn--teleport' : 'seat-panel-default__btn seat-panel-default__btn--teleport'}
                        title={t('seat.teleportTitle')}
                        aria-label={t('seat.teleportMe')}
                    >
                        {isCu ? (
                            <span className="cu-seat-panel__btn-label">{t('seat.teleportMe')}</span>
                        ) : (
                            t('seat.teleportMe')
                        )}
                    </button>
                )}
            </div>

            {activeSeatRouteId && (!isCu || !seatRouteError) && (
                <div
                    className={
                        isCu
                            ? `cu-seat-panel__status${activeSeatRouteId.includes(':') ? ' cu-seat-panel__status--error' : ''}`
                            : `seat-panel-default__status${activeSeatRouteId.includes(':') ? ' seat-panel-default__status--error' : ''}`
                    }
                    role={activeSeatRouteId.includes(':') ? 'alert' : 'status'}
                    aria-live={activeSeatRouteId.includes(':') ? 'assertive' : 'polite'}
                >
                    {isCu ? (
                        <>
                            <FlagPennantIcon />
                            {showCuStatusAsTwoRows ? (
                                <span className="cu-seat-panel__status-text cu-seat-panel__status-text--stacked">
                                    <span className="cu-seat-panel__status-line">{cuStatusTopRow}</span>
                                    <span className="cu-seat-panel__status-line">{cuStatusBottomRow}</span>
                                </span>
                            ) : (
                                <span className="cu-seat-panel__status-text">{seatStatusText}</span>
                            )}
                        </>
                    ) : (
                        <>
                            {seatStatusText}
                            {seatRouteError && seatErrorSuggestion ? (
                                <span className="seat-panel-default__status-suggestion">
                                    {' '}
                                    {seatErrorSuggestion}
                                </span>
                            ) : null}
                        </>
                    )}
                </div>
            )}

            {hasMeasure && !hideRouteMeasureInPanel && routeMeasure && (
                <RouteMeasureDisplay
                    isCu={isCu}
                    routeMeasure={routeMeasure}
                    onRefresh={onRefreshRouteMeasure}
                    refreshDisabled={actionsBusy}
                    onArmCooldown={onArmCooldown}
                />
            )}
        </div>
    );
};

export default SeatFormBody;
