import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppMode } from '../../../../context/AppModeContext';
import { useNavigation, useAppUI, useEnvironment } from '../../contexts';
import { sendMessage } from '../../messaging';
import { beginViewTransition } from '../../viewTransition';
import { SeatQuery } from './types';
import {
    CU_STADIUM_SECTION_LETTERS,
    CU_WHEELCHAIR_SECTION_LETTERS,
    getWalkingRowsForSection,
    getWalkingSeatsForRow,
    getWheelchairRowsForSection,
    getWheelchairSeatsForRow,
} from './constants';
import { requestSeatTeleportFromBirdEyeCheck } from './seatBirdEyeTeleportRpc';
import { useBottomSheet } from './hooks/useBottomSheet';
import { useModalAccessibility } from '../../hooks/useModalAccessibility';
import { FOCUSABLE_SELECTOR } from '../../hooks/useFocusTrap';
import { useSeatSheetForeground } from '../../hooks/useSeatSheetForeground';
import { useCuModeSwitching } from './hooks/useCuModeSwitching';
import SeatFormBody from './components/SeatFormBody';
import CuBottomSheet from './components/CuBottomSheet';
import DefaultSeatPanel from './components/DefaultSeatPanel';
import AvoidanceToggles from './components/AvoidanceToggles';
import './SeatNavigateWidget.css';

export type { SeatQuery } from './types';

const SeatNavigateWidget: React.FC = () => {
    const nav = useNavigation();
    const appUI = useAppUI();
    const env = useEnvironment();
    const { mode: appMode } = useAppMode();

    const variant = appMode === 'cu' ? 'cu' : 'default';
    const isCu = variant === 'cu';
    const onClose = appUI.closeSeatPanel;
    const onSeatNavigate = nav.handleSeatNavigate;
    const onSeatRouteDismiss = nav.handleSeatRouteDismiss;
    const activeSeatRouteId = nav.activeSeatRouteId;
    const movingToSeatId = nav.movingToSeatId;
    const onSeatMoveStart = nav.handleSeatMoveStart;
    const onSeatMoveStop = nav.handleSeatMoveStop;
    const onSeatTeleport = nav.handleSeatTeleport;
    const accessibilityMode = nav.navmeshMode;
    const routeMeasure = nav.routeMeasureByRouteId['seat_nav'];
    const routeMeasureEnabled = nav.routeMeasureEnabled;
    const onRefreshRouteMeasure = nav.handleRefreshSeatRouteMeasure;
    const avoidCrowds = nav.avoidCrowds;
    const avoidNoise = nav.avoidNoise;
    const onAvoidCrowdsToggle = nav.handleAvoidCrowdsToggle;
    const onAvoidNoiseToggle = nav.handleAvoidNoiseToggle;
    const onNavmeshModeChange = appMode === 'cu' ? nav.handleNavmeshModeChange : undefined;
    const navmeshBaking = nav.navmeshBaking;
    const hideRouteMeasureInPanel = appUI.seatStreamOverlayActive;
    const hideBottomSheetHandlebar =
        appUI.seatStreamOverlayActive || appUI.restroomStreamOverlayActive || appUI.quietStreamOverlayActive;
    const forceExpandSignal = appMode === 'cu' ? appUI.seatForceExpandSignal : 0;
    const initialDraft = appUI.seatPanelDraft;
    const onDraftChange = appUI.setSeatPanelDraft;

    const { t } = useTranslation();

    // Form field state (section is one letter; WC seat draft may be legacy "R1")
    const [section, setSection] = useState(
        () => (initialDraft?.section ?? '').replace(/[^\p{L}]/gu, '').slice(0, 1),
    );
    const [row, setRow] = useState(initialDraft?.row ?? '');
    const [seat, setSeat] = useState(() => {
        const s = initialDraft?.seat ?? '';
        const t = s.trim();
        if (/^[rR]\d+$/.test(t)) return t.slice(1);
        return s;
    });
    const [useWaypoints, setUseWaypoints] = useState(true);

    const clearFormFields = useCallback(() => {
        setSection('');
        setRow('');
        setSeat('');
    }, []);

    // CU mode switching hook
    const cuMode = useCuModeSwitching({
        isCu,
        accessibilityMode,
        navmeshBaking,
        onNavmeshModeChange,
        onDraftChange,
        onSeatRouteDismiss,
        clearFormFields,
    });

    const meshModeForForm = isCu && onNavmeshModeChange ? cuMode.cuTabMode : accessibilityMode;
    const isWheelchair = meshModeForForm === 'wheelchair';

    const isComplete =
        section.trim() !== '' &&
        row.trim() !== '' &&
        seat.trim() !== '' &&
        /^\d+$/.test(seat.trim());
    const isMoving = !!movingToSeatId;
    const hasValidRoute = !!activeSeatRouteId && !activeSeatRouteId.includes(':');

    // Bottom sheet hook (CU variant)
    const routeConfirmed = Boolean(routeMeasure?.success) || Boolean(movingToSeatId);
    /** Peek-collapse uses handlebar height; hiding the bar would leave a useless sliver — skip collapse while stream overlay is up */
    const shouldAutoCollapseSheet =
        isCu && hasValidRoute && routeConfirmed && !hideBottomSheetHandlebar;
    const {
        sheetShellRef,
        handlebarHitRef,
        sheetExiting,
        sheetEnterDone,
        sheetCollapsed,
        cuSheetShellStyle,
        requestClose,
        expandFromPeek,
        onSheetShellAnimationEnd,
        onHandlePointerDown,
        onHandlePointerMove,
        finishHandlePull,
        onHandlePointerCancel,
        onHandleKeyDown,
    } = useBottomSheet({
        onClose,
        isCu,
        forceExpandSignal,
        shouldAutoCollapse: shouldAutoCollapseSheet,
    });

    const seatDockRef = useRef<HTMLDivElement>(null);
    const seatSheetForeground = useSeatSheetForeground();
    const cuSeatPanelVisible = isCu && seatSheetForeground;
    useModalAccessibility(seatDockRef, { enabled: cuSeatPanelVisible });

    // When opened over Search/Controls menu, move focus into the sheet (menu is `inert` behind it).
    useEffect(() => {
        if (!cuSeatPanelVisible) return;
        const raf = requestAnimationFrame(() => {
            const dock = seatDockRef.current;
            if (!dock) return;
            const items = Array.from(
                dock.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
            ).filter((el) => el.getAttribute('aria-hidden') !== 'true');
            const closeBtn = dock.querySelector<HTMLElement>('.cu-seat-panel__close');
            const target =
                (closeBtn && items.includes(closeBtn) ? closeBtn : null) ??
                items.find((el) => !el.classList.contains('cu-seat-panel__handlebar-hit')) ??
                items[0];
            target?.focus({ preventScroll: true });
        });
        return () => cancelAnimationFrame(raf);
    }, [cuSeatPanelVisible, forceExpandSignal]);

    useEffect(() => {
        if (!isCu || !hideBottomSheetHandlebar) return;
        expandFromPeek();
    }, [isCu, hideBottomSheetHandlebar, expandFromPeek]);

    /**
     * Cascading option lists for the dropdowns. The Section list itself comes
     * from the constants module (separate per mode); the Row and Seat lists
     * shrink as the user picks upstream.
     */
    const availableRows = useMemo(() => {
        const upper = section.trim().toUpperCase();
        if (!upper) return [];
        if (isWheelchair) return getWheelchairRowsForSection(upper);
        return getWalkingRowsForSection(upper);
    }, [isWheelchair, section]);

    const availableSeats = useMemo(() => {
        const upper = section.trim().toUpperCase();
        if (!upper) return [];
        const trimmedRow = row.trim();
        if (!trimmedRow) return [];
        if (isWheelchair) return getWheelchairSeatsForRow(upper, trimmedRow);
        return getWalkingSeatsForRow(upper, trimmedRow);
    }, [isWheelchair, section, row]);

    // Section dropdown emits an exact section letter (or '' to clear); the
    // legacy single-letter validation is preserved as a defensive guard for
    // stale drafts coming from the URL / context.
    const onSectionChange = useCallback((raw: string) => {
        const next = raw.replace(/[^\p{L}]/gu, '').slice(0, 1).toUpperCase();
        setSection((prev) => {
            if (prev === next) return prev;
            // Cascade: changing section invalidates both downstream picks.
            setRow('');
            setSeat('');
            return next;
        });
    }, []);

    const onRowChange = useCallback((raw: string) => {
        setRow((prev) => {
            if (prev === raw) return prev;
            setSeat('');
            return raw;
        });
    }, []);

    const onSeatChange = useCallback((raw: string) => {
        setSeat(raw);
    }, []);

    // Migrate legacy wheelchair drafts like "R1" to digits-only display
    useEffect(() => {
        if (!isWheelchair) return;
        setSeat((s) => {
            const t = s.trim();
            if (/^[rR]\d+$/.test(t)) return t.slice(1);
            return s;
        });
    }, [isWheelchair]);

    /** Wheelchair sections expose one ticket row each (e.g. ``6``) — pre-select it. */
    useEffect(() => {
        if (!isWheelchair) return;
        const upper = section.trim().toUpperCase();
        if (!upper) return;
        const rows = getWheelchairRowsForSection(upper);
        if (rows.length === 1 && row.trim() !== rows[0]) {
            setRow(rows[0]);
        }
    }, [isWheelchair, section, row]);

    // Clear stale section when the active section list no longer contains it
    // (mode switch, or the section is removed from the hierarchy after a data
    // regeneration). Also clears row + seat to avoid mismatched residue.
    useEffect(() => {
        const list = isWheelchair ? CU_WHEELCHAIR_SECTION_LETTERS : CU_STADIUM_SECTION_LETTERS;
        const upper = section.trim().toUpperCase();
        if (upper && !list.includes(upper)) {
            setSection('');
            setRow('');
            setSeat('');
        }
    }, [isWheelchair, section]);

    // Clear stale row when the available row list (driven by the current
    // section) no longer contains it.
    useEffect(() => {
        const trimmed = row.trim();
        if (trimmed && !availableRows.includes(trimmed)) {
            setRow('');
            setSeat('');
        }
    }, [row, availableRows]);

    // Clear stale seat when the available seat list no longer contains it.
    useEffect(() => {
        const trimmed = seat.trim();
        if (trimmed && !availableSeats.includes(trimmed)) {
            setSeat('');
        }
    }, [seat, availableSeats]);

    // Sync draft to parent
    useEffect(() => {
        onDraftChange?.({ section, row, seat });
    }, [section, row, seat, onDraftChange]);

    // Sync cleared draft back to local state (e.g. after successful seat arrival)
    useEffect(() => {
        if (!initialDraft.section && !initialDraft.row && !initialDraft.seat) {
            clearFormFields();
        }
    }, [initialDraft, clearFormFields]);

    const routeFormKey = `${section.trim().toUpperCase()}-${row.trim().toUpperCase()}-${seat.trim()}`;

    // Dismiss route when form changes and no longer matches
    useEffect(() => {
        if (!nav.seatWidgetOpen && !appUI.seatPanelStickyOpen) return;
        if (!activeSeatRouteId || !onSeatRouteDismiss) return;
        if (!activeSeatRouteId.includes(':')) {
            if (!isComplete || routeFormKey !== activeSeatRouteId) {
                onSeatRouteDismiss();
            }
            return;
        }
        if (!isComplete) {
            onSeatRouteDismiss();
        }
    }, [nav.seatWidgetOpen, appUI.seatPanelStickyOpen, routeFormKey, isComplete, activeSeatRouteId, onSeatRouteDismiss]);

    // Build query from current form state (uppercase section/row matches Kit `_resolve_seat_number`)
    const buildQuery = (): SeatQuery => ({
        section: section.trim().toUpperCase(),
        row: row.trim().toUpperCase(),
        seat: seat.trim(),
        useWaypoints,
    });

    const handleGo = () => {
        if (!isComplete) return;
        if (isCu) cuMode.armCooldown();
        const query = buildQuery();
        // Bird-eye seat navigation reuses the same `MapMarkerDirectionsPanel`
        // UX as map-marker POIs (Foyer/Entrance/Arena): draw the dashed SVG
        // overlay on the map, hand off to the Directions sheet with swap
        // support. The actual seat route is committed when the user presses
        // "Start navigation" in that sheet (see MapMarkerDirectionsPanel).
        //
        // Validate the seat BEFORE advancing to the Directions panel —
        // otherwise an invalid seat would open the preview sheet and then
        // fail silently when Kit tries to resolve the end position. The
        // preflight RPC is the same one the teleport path uses; on failure
        // its handler surfaces the inline error in the seat panel.
        if (env.currentCamera === 'bird_eye') {
            void requestSeatTeleportFromBirdEyeCheck(query).then((result) => {
                if (!result.ok) return;
                const seatLabel = `${query.section}-${query.row}-${query.seat}`;
                try {
                    sendMessage('birdEyeRouteRequest', {
                        startPos: null,
                        endSeatNumber: seatLabel,
                        useWaypoints: query.useWaypoints !== false,
                        section: query.section,
                    });
                } catch { /* ignore */ }
                const displayLabel = t('seat.label', { id: seatLabel });
                nav.openSeatDirectionsPreview(query, displayLabel);
                appUI.closeSeatPanel();
            });
            return;
        }
        onSeatNavigate(query);
    };

    const handleGetDirectionsOrStop = () => {
        if (hasValidRoute) {
            if (isCu) cuMode.armCooldown();
            onSeatNavigate(buildQuery());
        } else {
            handleGo();
        }
    };

    const handleTeleport = onSeatTeleport
        ? () => {
              if (!isComplete) return;
              if (isCu) cuMode.armCooldown();
              const query = buildQuery();
              // From bird-eye we need the view + LOD switch before the
              // teleport, otherwise the player ends up at the seat with the
              // light-LOD stadium and the overhead camera still active.
              // `seatTeleportFromBirdEye` runs the same FP-enter-to-seat
              // sequence as `seatDirectionsStart` (start_is_seat=true),
              // minus the route calculation.
              //
              // Validate the seat synchronously via Kit BEFORE starting the
              // fade-to-black overlay — an invalid seat would otherwise leave
              // the user stuck on a black "Entering first person…" overlay
              // (the executor returns silently, so `viewTransitionReady`
              // never fires). On failure the preflight handler also surfaces
              // the inline error in the seat panel, mirroring the first-person UX.
              if (env.currentCamera === 'bird_eye') {
                  void requestSeatTeleportFromBirdEyeCheck(query).then((result) => {
                      if (!result.ok) return;
                      beginViewTransition({
                          message: t('streaming.switchingFirstPerson'),
                          onFadeOutComplete: () => {
                              try {
                                  sendMessage('seatTeleportFromBirdEye', {
                                      section: query.section,
                                      row: query.row,
                                      seat: query.seat,
                                  });
                              } catch { /* ignore */ }
                              env.setCurrentCamera('first_person');
                          },
                      });
                      appUI.closeSeatPanel();
                  });
                  return;
              }
              onSeatTeleport(query);
          }
        : undefined;

    // Seat status text
    /** Kit/route failure after a valid dropdown selection — not a form validation error. */
    const seatRouteError =
        !!activeSeatRouteId &&
        (activeSeatRouteId.startsWith('not_found:') ||
            activeSeatRouteId.startsWith('not_available:') ||
            activeSeatRouteId.startsWith('unreachable:'));

    const currentSeatId = routeFormKey;

    const seatStatusText = !activeSeatRouteId
        ? ''
        : activeSeatRouteId.startsWith('not_found:')
          ? t('seat.doesNotExist', { id: activeSeatRouteId.replace('not_found:', '') })
          : activeSeatRouteId.startsWith('not_available:')
            ? t('seat.notAvailable', { id: activeSeatRouteId.replace('not_available:', '') })
            : activeSeatRouteId.startsWith('unreachable:')
              ? isWheelchair
                  ? t('seat.notAvailable', { id: activeSeatRouteId.replace('unreachable:', '') })
                  : t('seat.unreachable', { id: activeSeatRouteId.replace('unreachable:', '') })
              : activeSeatRouteId.includes(':')
                ? t('seat.genericNotAvailable')
                : t('seat.routeTo', { id: isComplete ? currentSeatId : activeSeatRouteId });

    const seatErrorSuggestion = !seatRouteError
        ? ''
        : activeSeatRouteId?.startsWith('not_found:')
          ? t('seat.errorSuggestionNotFound')
          : activeSeatRouteId?.startsWith('not_available:')
            ? t('seat.errorSuggestionNotAvailable')
            : activeSeatRouteId?.startsWith('unreachable:')
              ? isWheelchair
                  ? t('seat.errorSuggestionNotAvailable')
                  : t('seat.errorSuggestionUnreachable')
              : t('seat.errorSuggestionGeneric');

    const hasMeasure =
        hasValidRoute &&
        routeMeasureEnabled &&
        !!routeMeasure?.success &&
        (routeMeasure.distanceMetersBase > 0 || (routeMeasure.distanceMetersActual ?? 0) > 0);

    const actionsBusy = cuMode.cuSeatActionsBusy || !!cuMode.cuInteractLocked;

    // Shared form body
    const formBody = (
        <SeatFormBody
            isCu={isCu}
            isWheelchair={isWheelchair}
            section={section}
            row={row}
            seat={seat}
            availableRows={availableRows}
            availableSeats={availableSeats}
            onSectionChange={onSectionChange}
            onRowChange={onRowChange}
            onSeatChange={onSeatChange}
            onEnterSubmit={handleGo}
            disabled={!!cuMode.cuInteractLocked}
            seatRouteError={seatRouteError}
            seatStatusText={seatStatusText}
            seatErrorSuggestion={seatErrorSuggestion}
            activeSeatRouteId={activeSeatRouteId}
            hasValidRoute={hasValidRoute}
            isComplete={isComplete}
            onGetDirectionsOrStop={handleGetDirectionsOrStop}
            onTeleport={handleTeleport}
            actionsBusy={actionsBusy}
            routeMeasure={routeMeasure}
            hasMeasure={hasMeasure}
            hideRouteMeasureInPanel={hideRouteMeasureInPanel}
            onRefreshRouteMeasure={onRefreshRouteMeasure}
            onArmCooldown={cuMode.armCooldown}
        />
    );

    if (appUI.seatArrivalCelebrationVisible || appUI.poiArrivalVisible) return null;
    if (nav.restroomWidgetOpen) return null;
    if (nav.quietZoneWidgetOpen) return null;
    if (appUI.seatStreamOverlayActive) return null;
    if (!nav.seatWidgetOpen && !appUI.seatPanelStickyOpen) return null;

    if (isCu) {
        return (
            <CuBottomSheet
                rootRef={seatDockRef}
                sheetShellRef={sheetShellRef}
                handlebarHitRef={handlebarHitRef}
                sheetExiting={sheetExiting}
                sheetEnterDone={sheetEnterDone}
                sheetCollapsed={sheetCollapsed}
                cuSheetShellStyle={cuSheetShellStyle}
                requestClose={requestClose}
                onSheetShellAnimationEnd={onSheetShellAnimationEnd}
                onHandlePointerDown={onHandlePointerDown}
                onHandlePointerMove={onHandlePointerMove}
                finishHandlePull={finishHandlePull}
                onHandlePointerCancel={onHandlePointerCancel}
                onHandleKeyDown={onHandleKeyDown}
                onNavmeshModeChange={onNavmeshModeChange}
                cuTabMode={cuMode.cuTabMode}
                navmeshBaking={navmeshBaking}
                cuModeSwitchBusy={cuMode.cuModeSwitchBusy}
                selectNavmeshTab={cuMode.selectNavmeshTab}
                cuInteractLocked={cuMode.cuInteractLocked}
                hideHandlebar={hideBottomSheetHandlebar}
            >
                {formBody}
            </CuBottomSheet>
        );
    }

    return (
        <DefaultSeatPanel onClose={onClose}>
            {formBody}
            <div style={{ padding: '0 12px 12px' }}>
                <AvoidanceToggles
                    avoidCrowds={avoidCrowds}
                    avoidNoise={avoidNoise}
                    onAvoidCrowdsToggle={onAvoidCrowdsToggle}
                    onAvoidNoiseToggle={onAvoidNoiseToggle}
                    useWaypoints={useWaypoints}
                    onUseWaypointsToggle={() => setUseWaypoints(!useWaypoints)}
                    hasValidRoute={hasValidRoute}
                    isMoving={isMoving}
                    activeSeatRouteId={activeSeatRouteId}
                    onMoveStart={() => {
                        if (isCu) cuMode.armCooldown();
                        onSeatMoveStart();
                    }}
                    onMoveStop={() => {
                        if (isCu) cuMode.armCooldown();
                        onSeatMoveStop();
                    }}
                    moveDisabled={actionsBusy}
                />
            </div>
        </DefaultSeatPanel>
    );
};

export default SeatNavigateWidget;
