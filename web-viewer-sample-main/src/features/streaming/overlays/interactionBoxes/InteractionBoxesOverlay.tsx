import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { kitMarkerIconUrlByBasename } from '@icons/kitMarkersRegistry';
import './InteractionBoxesOverlay.css';
import '../../DarkMode.css';
import { useAppUI, useChat, useControl, useEnvironment, useNavigation, useStream } from '../../contexts';
import type { MapMarkerSheetData } from '../../hooks/navigationHandlers/useMapMarkerPoiNavigation';
import interactivePointerSvg from '@icons/interaction/interactive-pointer.svg';
import imageAvatarSvg from '@icons/interaction/image-avatar.svg';
import userLocationSvg from '@icons/map-markers/location_arrow.svg';
import {
  speakText,
  parseVoiceProfile,
  type AvatarVoiceProfile,
  type SpeechController,
} from '../../../../services/speechSynthesis';
import TtsSpeakerIcon from '../TtsSpeakerIcon';
import { computeVideoContentRect, type ContentRect } from '../overlayUtils';
import { useSmoothedOverlayPosition } from '../useSmoothedOverlayPosition';

/**
 * The location-arrow SVG (Figma export) points ~39.2° counter-clockwise of
 * straight-up in its natural orientation — that's the screen angle between
 * its base→tip axis and the SVG y-axis. Kit emits ``headingDeg`` in CSS
 * rotate() convention (0° = screen-up, CW positive); adding this offset
 * makes the arrow tip align with the published heading.
 */
const USER_LOCATION_ARROW_SVG_OFFSET_DEG = 39.2;

/**
 * Map raw severity strings (from Kit/interactions.json) to a display label and
 * (separately) to an accessible long-form for the badge so screen readers don't
 * just announce "INFO" / "DANGER" without context.
 */
type SeverityKey = 'info' | 'warning' | 'danger' | 'success';
function normalizeSeverity(raw: string | undefined): SeverityKey {
  const v = String(raw ?? '').toLowerCase();
  if (v === 'warning' || v === 'warn') return 'warning';
  if (v === 'critical' || v === 'danger' || v === 'error') return 'danger';
  if (v === 'success' || v === 'ok') return 'success';
  return 'info';
}

type ScreenPt = { x: number; y: number };
type ViewportSize = { width: number; height: number };

export type InteractionUi = {
  title?: string;
  subtitle?: string;
  body?: string;
  severity?: 'info' | 'warning' | 'critical' | string;
  style?: string;
  spawnPoint?: string;
};

export type UiInteractionBoxesUpdate = {
  timestampMs: number;
  viewport: ViewportSize | null;
  items: Array<{
    id: string;
    path: string;
    world: { x: number; y: number; z: number };
    screen: ScreenPt | null;
    inView: boolean;
    ui?: InteractionUi;
  }>;
};

/* Bird-eye map marker icons: see `icons/map-markers` + `icons/kitMarkersRegistry.ts`. */
const markerImages = kitMarkerIconUrlByBasename;

type CardData = {
  key: string;
  x: number;
  y: number;
  id: string;
  title: string;
  subtitle?: string;
  body: string;
  severity: string;
  style: string;
  ui?: Record<string, any>;
  onTeleport?: () => void;
  onAction?: (action: string, payload: Record<string, any>) => void;
  onSpeak?: () => void;
  ttsPlaying?: boolean;
  mapMarkerPayload?: MapMarkerSheetData;
};


type RendererStrings = {
  listen: string;
  stopListening: string;
  watch: string;
  watchTitle: (title: string) => string;
  severityLabel: (key: SeverityKey) => string;
  severityBadge: (key: SeverityKey) => string;
};

type SmoothedOverlayAnchorProps = React.PropsWithChildren<{
  targetX: number;
  targetY: number;
  className?: string;
  style?: React.CSSProperties;
}> &
  React.HTMLAttributes<HTMLDivElement>;

/** Positions projected Kit UI with the same easing as map markers (stream vs compositor jitter). */
function SmoothedOverlayAnchor({
  targetX,
  targetY,
  className,
  style,
  children,
  ...divProps
}: SmoothedOverlayAnchorProps) {
  const { x, y } = useSmoothedOverlayPosition(targetX, targetY);
  return (
    <div className={className} style={{ ...style, left: x, top: y }} {...divProps}>
      {children}
    </div>
  );
}

function buildStyleRenderers(
  strings: RendererStrings,
  keyboardTabStop: boolean,
): Record<string, (c: CardData) => JSX.Element> {
  const actionTabIndex = (hasAction: boolean) =>
    !hasAction ? undefined : keyboardTabStop ? 0 : -1;
  return {
    infoCard: (c) => {
      const sev = normalizeSeverity(c.severity);
      return (
        <SmoothedOverlayAnchor key={c.key} className="ibox-card" targetX={c.x} targetY={c.y}>
          <div className="ibox-header">
            <p className="ibox-title">{c.title}</p>
            <span
              className={`ibox-badge ${sev}`}
              role="status"
              aria-label={strings.severityBadge(sev)}
            >
              {strings.severityLabel(sev).toUpperCase()}
            </span>
          </div>
          {c.subtitle ? <p className="ibox-subtitle">{c.subtitle}</p> : null}
          {c.body ? <p className="ibox-body">{c.body}</p> : null}
        </SmoothedOverlayAnchor>
      );
    },
    speechBubble: (c) => (
      <SmoothedOverlayAnchor
        key={c.key}
        className={`ibox-speech-bubble ${c.ui?.action ? 'ibox-speech-bubble--clickable' : ''}`}
        targetX={c.x}
        targetY={c.y}
        role={c.ui?.action ? 'button' : undefined}
        aria-label={c.ui?.action ? c.title : undefined}
        tabIndex={actionTabIndex(!!c.ui?.action)}
        onKeyDown={
          c.ui?.action
            ? (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  c.onAction?.(String(c.ui!.action), (c.ui!.actionPayload || {}) as Record<string, any>);
                }
              }
            : undefined
        }
        onClick={() => {
          if (c.ui?.action) {
            c.onAction?.(String(c.ui.action), (c.ui.actionPayload || {}) as Record<string, any>);
          }
        }}
      >
        <p className="ibox-speech-text">{c.title}</p>
      </SmoothedOverlayAnchor>
    ),
    speechBubbleBottom: (c) => {
      const speakerLabel = c.ttsPlaying ? strings.stopListening : strings.listen;
      return (
        <div
          key={c.key}
          className={`ibox-speech-bottom-wrap ${c.ui?.action ? 'ibox-speech-bubble--clickable' : ''}`}
          role={c.ui?.action ? 'button' : undefined}
          aria-label={c.ui?.action ? c.title : undefined}
          tabIndex={actionTabIndex(!!c.ui?.action)}
          onKeyDown={
            c.ui?.action
              ? (e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    c.onAction?.(String(c.ui!.action), (c.ui!.actionPayload || {}) as Record<string, any>);
                  }
                }
              : undefined
          }
          onClick={() => {
            if (c.ui?.action) {
              c.onAction?.(String(c.ui.action), (c.ui.actionPayload || {}) as Record<string, any>);
            }
          }}
        >
          <span className="ibox-speech-bottom-avatar-wrap" aria-hidden>
            <img className="ibox-speech-bottom-avatar" src={imageAvatarSvg} alt="" draggable={false} />
          </span>
          <div className="ibox-speech-bubble ibox-speech-bubble--bottom">
            <p className="ibox-speech-text">{c.title}</p>
            <button
              type="button"
              className={`ibox-speech-bottom-speaker${c.ttsPlaying ? ' ibox-speech-bottom-speaker--playing' : ''}`}
              title={speakerLabel}
              aria-label={speakerLabel}
              aria-pressed={c.ttsPlaying === true}
              onClick={(e) => {
                e.stopPropagation();
                c.onSpeak?.();
              }}
            >
              <TtsSpeakerIcon className="ibox-speech-bottom-speaker-icon" />
            </button>
          </div>
        </div>
      );
    },
    interactivePointer: (c) => (
      <SmoothedOverlayAnchor key={c.key} className="ibox-interactive-pointer-wrap" targetX={c.x} targetY={c.y}>
        <img className="ibox-interactive-pointer-icon" src={interactivePointerSvg} alt="" draggable={false} />
      </SmoothedOverlayAnchor>
    ),
    videoTrigger: (c) => {
      const action = c.ui?.action || 'video.open';
      const payload = c.ui?.actionPayload || {};
      return (
        <SmoothedOverlayAnchor key={c.key} className="ibox-video-trigger" targetX={c.x} targetY={c.y}>
          <p className="ibox-video-trigger-title">{c.title}</p>
          <button
            type="button"
            className="ibox-video-trigger-btn"
            aria-label={strings.watchTitle(c.title)}
            title={strings.watchTitle(c.title)}
            onClick={() => c.onAction?.(action, payload)}
          >
            <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden><polygon points="5,3 19,12 5,21" fill="currentColor" /></svg>
            {strings.watch}
          </button>
        </SmoothedOverlayAnchor>
      );
    },
    userLocation: (c) => {
      const rawHeading = Number((c.ui as Record<string, any> | undefined)?.headingDeg);
      const headingDeg = Number.isFinite(rawHeading) ? rawHeading : 0;
      const rotation = headingDeg + USER_LOCATION_ARROW_SVG_OFFSET_DEG;
      return (
        <SmoothedOverlayAnchor key={c.key} className="ibox-user-location" targetX={c.x} targetY={c.y}>
          <img
            className="ibox-user-location-icon"
            src={userLocationSvg}
            alt=""
            draggable={false}
            style={{ transform: `rotate(${rotation}deg)` }}
          />
        </SmoothedOverlayAnchor>
      );
    },
  };
}

const AUTOMOVE_BOTTOM_EXCLUSION_PX = 220;

/**
 * Bird’s-eye “Find my seat” map pin — opens SeatNavigateWidget (same as search chip).
 * Match Kit icon and/or localized title so asset renames do not break.
 */
function isFindMySeatMapPin(
  ui: Record<string, any> | undefined,
  markerTitle: string,
  findSeatLabelLower: string,
  interactionId: string | undefined,
): boolean {
  if (ui?.markerVariant !== 'findSeat') return false;
  // Interaction id is authoritative — map marker icons may be swapped in data without changing behavior.
  if (interactionId === 'map_marker_arena') return true;
  const icon = String(ui?.icon || '').toLowerCase();
  const titleLower = markerTitle.trim().toLowerCase();
  const byTitle = titleLower === findSeatLabelLower;
  const byIcon =
    icon === 'find_my_seat.png' ||
    icon.endsWith('find_my_seat.png') ||
    icon === 'find seat.svg' ||
    icon.endsWith('find seat.svg') ||
    icon === 'arena.png' ||
    icon === 'arena' ||
    icon.endsWith('/arena.png') ||
    icon.endsWith('arena.png') ||
    /^arena\.(png|webp|jpe?g)$/i.test(icon);
  return byIcon || byTitle;
}

function MapMarkerPin({
  c,
  onActivate,
  selectedMapMarkerId,
  keyboardTabStop,
}: {
  c: CardData;
  onActivate: (card: CardData) => void;
  selectedMapMarkerId: string | null;
  keyboardTabStop: boolean;
}) {
  const iconSrc = markerImages[c.ui?.icon] || '';
  const payload = c.mapMarkerPayload;
  const ui = c.ui as Record<string, any> | undefined;
  const pinOnly = ui?.markerVariant === 'pinOnly';
  const findSeat = ui?.markerVariant === 'findSeat';
  /** Shares find-seat cluster chrome, peer fade, and sheet-selected lime with foyer / arena pins. */
  const findSeatCluster = findSeat || ui?.markerVariant === 'entrance';
  const sheetSelected =
    findSeatCluster && payload && selectedMapMarkerId != null && selectedMapMarkerId === payload.id;
  /** After opening a marker sheet, non-selected pins fade so the active one reads as lime. */
  const peerFaded =
    findSeatCluster &&
    payload &&
    selectedMapMarkerId != null &&
    selectedMapMarkerId !== payload.id;
  const entranceVariant = ui?.markerVariant === 'entrance';
  /** Same Lexend / dark-purple label as Entrance (Start pin unchanged). */
  const cuPoiLexendLabel = c.id === 'map_marker_foyer' || c.id === 'map_marker_arena';
  return (
    <SmoothedOverlayAnchor
      className={`ibox-map-marker${pinOnly ? ' ibox-map-marker--pin-only' : ''}${findSeatCluster ? ' ibox-map-marker--find-seat' : ''}${
        sheetSelected ? ' ibox-map-marker--find-seat-selected' : ''
      }${peerFaded ? ' ibox-map-marker--find-seat-peer' : ''}${entranceVariant ? ' ibox-map-marker--entrance' : ''}${
        cuPoiLexendLabel ? ' ibox-map-marker--cu-poi-label' : ''
      }`}
      targetX={c.x}
      targetY={c.y}
      role="button"
      tabIndex={keyboardTabStop ? 0 : -1}
      aria-pressed={findSeatCluster ? sheetSelected : undefined}
      aria-label={c.title}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onActivate(c);
        }
      }}
      onClick={() => {
        onActivate(c);
      }}
    >
      {pinOnly ? (
        iconSrc ? (
          <img className="ibox-map-marker-pin-only-icon" src={iconSrc} alt="" draggable={false} />
        ) : null
      ) : (
        <>
          {/*
            Adjacent label already announces the marker name, so the icon is
            decorative (alt=""). This avoids duplicate "<title> <title>"
            announcements in screen readers (WCAG 1.1.1).
          */}
          {iconSrc ? <img className="ibox-map-marker-icon" src={iconSrc} alt="" /> : null}
          <span className="ibox-map-marker-label">{c.title}</span>
        </>
      )}
    </SmoothedOverlayAnchor>
  );
}

export type InteractionBoxesOverlayProps = { videoElementId?: string };

export const InteractionBoxesOverlay: React.FC<InteractionBoxesOverlayProps> = ({
  videoElementId = 'remote-video',
}) => {
  const stream = useStream();
  const ctrl = useControl();
  const env = useEnvironment();
  const nav = useNavigation();
  const chat = useChat();
  const appUI = useAppUI();

  const { t, i18n } = useTranslation();
  const findSeatTitleLower = useMemo(() => t('search.findSeat').trim().toLowerCase(), [t]);

  const handleMapMarkerActivate = useCallback(
    (card: CardData) => {
      const payload = card.mapMarkerPayload;
      const ui = card.ui as Record<string, any> | undefined;
      if (payload?.id && isFindMySeatMapPin(ui, card.title, findSeatTitleLower, card.id)) {
        nav.openFindMySeatFromBirdEyeMap(payload.id);
        appUI.handleSearchChipNavigate('seat');
        return;
      }
      if (payload && (payload.primPath || payload.spawnPoint)) {
        nav.openMapMarkerSheet(payload);
      }
    },
    [nav, appUI, findSeatTitleLower],
  );

  const update: UiInteractionBoxesUpdate | null = stream.sceneLoading ? null : ctrl.uiInteractionBoxes;
  /** Hide default POI pins + player pin while map-marker "Get directions" preview is open (custom route overlay replaces them). */
  const directionsPreviewActive =
    nav.mapMarkerDirectionsPreview != null && !nav.movingToPoiId;

  const hiddenStyles = useMemo(
    () => [
      ...(env.currentCamera !== 'bird_eye' || directionsPreviewActive ? ['mapMarker', 'userLocation'] : []),
      ...(ctrl.avatarChatOpen ? ['interactivePointer'] : []),
    ],
    [env.currentCamera, ctrl.avatarChatOpen, directionsPreviewActive],
  );
  const autoMoveActive = appUI.streamNavOverlayActive;
  const onAction = useCallback(
    (action: string, payload: Record<string, any>) => {
      chat.interactionActions.dispatch('overlay', action, payload);
    },
    [chat.interactionActions],
  );

  const rootRef = useRef<HTMLDivElement | null>(null);
  const [contentRect, setContentRect] = useState<ContentRect | null>(null);
  const ttsControllerRef = useRef<SpeechController | null>(null);
  const [ttsPlayingCardKey, setTtsPlayingCardKey] = useState<string | null>(null);

  /**
   * Resolve a localized field from the interaction UI object.
   *
   * 1. Optional `titleI18nKey` / `subtitleI18nKey` / `bodyI18nKey` — full i18next
   *    key (e.g. `interactions.map_marker_stadium_entrance.title`, `search.findSeat`);
   *    English fallback is the bare `title` / `subtitle` / `body` from Kit JSON.
   * 2. Kit per-language overrides: `title_sv`, `subtitle_fr`, etc. (legacy).
   */
  const resolveLocalized = useCallback((ui: Record<string, any>, field: string): string | undefined => {
    const i18nKeyField = `${field}I18nKey`;
    const i18nKey = ui[i18nKeyField];
    if (typeof i18nKey === 'string' && i18nKey.trim()) {
      const def = ui[field] != null ? String(ui[field]) : '';
      return String(t(i18nKey.trim(), def ? { defaultValue: def } : {}));
    }
    const lang = (i18n.language || 'en').split('-')[0];
    if (lang && lang !== 'en') {
      const localized = ui[`${field}_${lang}`];
      if (localized) return String(localized);
    }
    return ui[field] != null ? String(ui[field]) : undefined;
  }, [i18n.language, t]);

  const handleSpeakToggle = useCallback(
    (cardKey: string, text: string, voiceProfile?: AvatarVoiceProfile) => {
      if (ttsPlayingCardKey === cardKey) {
        ttsControllerRef.current?.cancel();
        setTtsPlayingCardKey(null);
        return;
      }
      ttsControllerRef.current = speakText(text, {
        uiLang: i18n.language,
        voiceProfile,
        onStart: () => setTtsPlayingCardKey(cardKey),
        onEnd: () => setTtsPlayingCardKey((prev) => (prev === cardKey ? null : prev)),
        onError: () => setTtsPlayingCardKey((prev) => (prev === cardKey ? null : prev)),
      });
    },
    [ttsPlayingCardKey, i18n.language],
  );

  // Build localized renderers once per language change.
  const styleRenderers = useMemo(() => {
    const sevLabel = (key: SeverityKey) => t(`severity.${key}`);
    const sevBadge = (key: SeverityKey) => t(`severity.${key}Badge`);
    return buildStyleRenderers(
      {
        listen: t('common.listen'),
        stopListening: t('common.stopListening'),
        watch: t('video.play'),
        watchTitle: (title: string) => t('video.watchTitle', { title }),
        severityLabel: sevLabel,
        severityBadge: sevBadge,
      },
      !autoMoveActive,
    );
  }, [t, autoMoveActive]);

  // Cancel any in-flight utterance on unmount.
  useEffect(() => {
    return () => {
      ttsControllerRef.current?.cancel();
    };
  }, []);

  useEffect(() => {
    const video = document.getElementById(videoElementId) as HTMLVideoElement | null;
    if (!video) return;

    let raf = 0;
    const refresh = () => {
      try {
        setContentRect(computeVideoContentRect(video));
      } catch {
        setContentRect(null);
      }
    };

    const onResize = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(refresh);
    };

    // Initial and when metadata changes
    refresh();
    window.addEventListener('resize', onResize);
    video.addEventListener('loadedmetadata', onResize);
    video.addEventListener('resize', onResize as any);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', onResize);
      video.removeEventListener('loadedmetadata', onResize);
      video.removeEventListener('resize', onResize as any);
    };
  }, [videoElementId]);

  // Also refresh when new data arrives (covers layout shifts without resize events)
  useEffect(() => {
    if (!update) return;
    const video = document.getElementById(videoElementId) as HTMLVideoElement | null;
    if (!video) return;
    try {
      setContentRect(computeVideoContentRect(video));
    } catch {
      // ignore
    }
  }, [update?.timestampMs, videoElementId]);

  const cards = useMemo(() => {
    const viewport = update?.viewport;
    if (!update || !viewport || !contentRect) return [];

    const rootRect = rootRef.current?.getBoundingClientRect() ?? { left: 0, top: 0 };

    const hidden = hiddenStyles;
    return update.items
      .filter((it) => {
        if (!it.inView || !it.screen || viewport.width <= 0 || viewport.height <= 0) return false;
        if (hidden && hidden.length > 0) {
          const s = (it.ui as any)?.style || 'infoCard';
          if (hidden.includes(s)) return false;
        }
        return true;
      })
      .map((it) => {
        const scr = it.screen as ScreenPt;
        const xClient = contentRect.left + (scr.x / viewport.width) * contentRect.width;
        const yClient = contentRect.top + (scr.y / viewport.height) * contentRect.height;

        const x = xClient - rootRect.left;
        const y = yClient - rootRect.top;

        const ui = (it.ui || {}) as Record<string, any>;
        // Severity is also localized (Kit may emit `severity_sv` etc.) so the
        // displayed badge label matches the rest of the card. Falls back to
        // the raw English value when no localized form exists.
        const severity = (resolveLocalized(ui, 'severity') || 'info') as string;
        const style = (ui.style || 'infoCard') as string;
        const localTitle = resolveLocalized(ui, 'title') || it.id;
        const localSubtitle = resolveLocalized(ui, 'subtitle');
        const localBody = resolveLocalized(ui, 'body') || '';
        const mapMarkerPayload: MapMarkerSheetData | undefined =
          style === 'mapMarker'
            ? {
                id: it.id,
                title: localTitle,
                spawnPoint: String(ui.spawnPoint || ''),
                primPath: String(ui.routingPrimPath || it.path || ''),
                isAccessible: ui.is_accessible === true || ui.is_accessible === 'true',
              }
            : undefined;
        return {
          key: it.id,
          x,
          y,
          id: it.id,
          title: localTitle,
          subtitle: localSubtitle,
          body: localBody,
          severity,
          style,
          ui,
          mapMarkerPayload,
          onAction,
          onSpeak: style === 'speechBubbleBottom'
            ? () => handleSpeakToggle(it.id, localTitle, parseVoiceProfile(ui?.voice ?? ui?.voiceProfile))
            : undefined,
          ttsPlaying: style === 'speechBubbleBottom' ? ttsPlayingCardKey === it.id : false,
        };
      })
      .filter((card) => {
        if (!autoMoveActive) return true;
        if (card.style === 'speechBubbleBottom') return true;
        return card.y < window.innerHeight - AUTOMOVE_BOTTOM_EXCLUSION_PX;
      });
  }, [update, contentRect, hiddenStyles, autoMoveActive, onAction, handleSpeakToggle, ttsPlayingCardKey, resolveLocalized]);

  if (!update || !update.viewport) return null;

  return (
    <div ref={rootRef} className={`ibox-overlay-root${autoMoveActive ? ' ibox-overlay-root--automove' : ''}`}>
      {cards.map((c) => {
        if (c.style === 'mapMarker') {
          return (
            <MapMarkerPin
              key={c.key}
              c={c}
              onActivate={handleMapMarkerActivate}
              selectedMapMarkerId={nav.mapMarkerSheet?.id ?? nav.birdEyeMapMarkerFocusId ?? null}
              keyboardTabStop={!autoMoveActive}
            />
          );
        }
        const renderer = styleRenderers[c.style] || styleRenderers.infoCard;
        return renderer(c);
      })}
    </div>
  );
};

