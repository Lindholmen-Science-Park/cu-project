# WCAG CU / streaming — further rounds

Companion to `Checklist.WCAG2.2(WCAG 2.csv`. Tracks what is **done in code** vs **still open** after the keyboard + seat-form accessibility passes.

**Policy (Younite):** Do not add **visible** copy that is not in design. Use labels, placeholders, ARIA, and `.sr-only` text; escalate visible instructions/errors to Kokokaka/design.

---

## Completed (in repo)

### Round A — Keyboard, skip link, onboarding, modals (commit `f5941dc5` and earlier)

- Skip-to-main (`index.html`, tab order, focus into viewer)
- Onboarding: language dropdown keyboard, single dot row, `inert` slides, skip suppressed
- Quick settings / modals: focus trap, restore, background `inert`
- `LanguageDropdown` / `EventDropdown` listbox keyboard pattern

### Round B — Seat form, checklist, map pins (commit `e141571a`)

- `SeatChoiceDropdown`: Tab/arrow keyboard, `aria-labelledby`, `name=` fields
- Seat **Kit route** errors (`unreachable` / `not_available` / `not_found`): visible `#cu-seat-form-error` + `role="alert"`, engineering i18n suggestions (EN/SV/FR/ES) — **left as-is for now**; copy may not match current seat-nav behaviour until design/product revisits
- `seat.formInstructions`: **sr-only** only (not on screen)
- Quick settings: visible event label + `EventDropdown` `labelId`
- Pin-only map markers: min 44×44 px hit area
- Checklist CSV + `wcag-accessibility.mdc` comments updated

### Checklist: **Yes** (11)

2.1.2, 2.4.1, 2.4.2, 2.4.7, 3.1.1 — plus team-confirmed Mar 2026:

- **1.4.1** Use of color — May 2026 Younite + Kokokaka audit: interactive state/function not conveyed by color alone (labels, icons, `aria-pressed`, switch glyphs, borders)
- **1.4.2** Audio control — CU media mute/volume (QA pass)
- **2.1.4** Character key shortcuts — no single-key shortcuts without modifier in CU (QA pass)
- **2.2.2** Pause, stop, hide — players + dismissible toasts (QA pass)
- **2.3.1** Three flashes — no flashing in current build; **re-verify** when adding lights/VFX/effects
- **2.5.2** Pointer cancellation — buttons: drag off control does not fire; sliders: native `type="range"` live adjust (QA pass)

### Round C (partial) — POI / directions route status messages (4.1.3 evaluated)

**Criterion 4.1.3** audited for **restroom / quiet-zone / map-marker directions** Kit route failures.

| Status | Detail |
|--------|--------|
| **Evaluated** | **Partial** — checklist row stays Partial (not Yes) |
| **Interim (code)** | `RouteErrorAlert` + list-card `.sr-only` + `aria-describedby`; plumbing `routeErrorByRouteId` / `navRouteErrorMessages.ts`. No visible banners (policy: no invented copy). |
| **Blocked on design** | Per-case **visible** error UI + approved i18n (unreachable vs not_available vs generic, restroom vs quiet vs directions, list row vs sheet vs panel). Engineering wires design strings when Round D delivers options. |

Same **design-before-visible** rule applies to **3.3.1 / 3.3.3** on non-seat flows (row 8 below).

### Round C (partial) — Custom widget name/role/value (4.1.2)

**Criterion 4.1.2** audited for **search suggestion chips**, **immersive media toolbars** (videobook / 360° / spatial sound), and shared `MediaPlayerControls`.

**Systematic CU pass (2026-05-26):** full gap inventory in [`WCAG_4_1_2_CU_AUDIT.md`](./WCAG_4_1_2_CU_AUDIT.md) — CU vs dev-only vs acceptable exceptions; small fixes (chat send/close, seat teleport label, route-bar mute `aria-pressed`, videobook splash chapter button name, NPC bubble open-chat label). Tap-to-show-chrome **documented accepted**; globe pins **excluded** (dev-only).

| Area | Fixes |
|------|--------|
| Search chips | `role="group"` + `aria-label`; chips keep `aria-pressed` + visible label; Explore quick action no longer misuses `aria-pressed` |
| Media transport | Play/pause: dynamic `aria-label` only (removed incorrect `aria-pressed`); mute/CC keep `aria-pressed`; 360° + spatial play/pause localized |
| Seek sliders | `aria-valuetext` (`common.mediaSeekPosition`) on videobook / 360° / spatial seek bars |
| Videobook seek | Chapter markers on bar marked `aria-hidden` (decorative; chapter buttons live in chapter menu) |
| 360° loading | `role="status"` + sr-only loading text + `essential-motion` spinner |

| Interaction overlays | Clickable speech bubbles `aria-label`; video trigger `aria-label` + `title`; map pins already had `aria-label` + `aria-pressed` |
| Flat video player | Play/pause `aria-pressed` removed (label only) |
| Seat nav (dev panel toggles) | Crowd/noise avoidance `aria-pressed` + `aria-label`; route refresh icon `aria-label` |
| Globe back | `type="button"` (visible back label) |

**Still Partial:** dev-only widgets (`PoiRoutesWidget`, `OsmNavigateWidget`, camera/sound dev panels); any new custom controls — spot-check on add.

---

## Round C — Engineering (Younite) — suggested next

| Priority | Criterion | Work |
|----------|-----------|------|
| 1 | 4.1.3 | **POI / restroom / directions** — evaluated; interim sr-only in repo. **No further code** for visible status until design. |
| 2 | 4.1.2 | **Partial** — see [`WCAG_4_1_2_CU_AUDIT.md`](./WCAG_4_1_2_CU_AUDIT.md). CU production paths largely OK; open items are optional polish + **dev-only** widgets (exclude from CU Yes). Path to Yes: product sign-off + short SR QA. |
| 3 | 2.4.3 | Stream surface focus contract (what is tabbable in WebRTC vs chrome) — document + any sentinel fixes |
| 4 | 2.1.1 | Full CU keyboard pass checklist per screen (controls menu, settings, POI sheets, globe return) |
| 5 | 1.1.1 | Systematic pass: every `<img>` / icon-only control in `features/cu/**` — `alt=""` + parent name vs meaningful alt |
| 6 | 1.4.13 | Remove/replace `title`-only tooltips where hover is the only hint |
| 7 | 2.5.8 | Audit small controls (search chips, map controls, stream overlay buttons) for 44×44 minimum |
| 8 | 3.3.1–3.3.3 | **Non-seat** flows — evaluated with POI 4.1.3 pass; visible identification/suggestion **blocked on design** (same cases as route errors). Sr-only interim only. |
| 9 | **2.5.1** | **After design:** bird-eye **+ / −** zoom buttons → `birdEyeZoomLevel` (see Round D brief); optional rotate buttons for twist |

**Not in scope for engineering alone:** visible help/error copy — design must add strings in Figma + i18n.

---

## Round D — Design / Kokokaka — suggested next

| Criterion | Work |
|-----------|------|
| 1.4.3 | Text contrast 4.5:1 (body), 3:1 (UI components) on purple/dark panels |
| 1.4.11 | Non-text contrast (icons, focus rings, borders) |
| 1.4.12 | Text spacing overrides if required beyond browser defaults |
| 2.4.5 | Multiple ways to find content (IA) |
| 3.2.3 | Consistent navigation patterns |
| 3.3.2 | Any **visible** instructions designers want (then add to i18n — do not invent in code) |
| **3.3.1 / 3.3.3 / 4.1.3** | **Route error copy by case** — restroom, quiet zone, directions panel, bird-eye (and list-row unreachable). Figma + EN/SV/FR/ES; engineering mounts visible UI after approval (replace sr-only `RouteErrorAlert` / card hints). |
| **2.5.1** | **Bird-eye map controls** — see design brief below (blocks **Yes** on touch) |

### 2.5.1 — Bird-eye zoom / rotate (design brief for Kokokaka)

**WCAG 2.5.1 (A):** Any function that needs a **multipoint** or **path-based** gesture must also work with a **single-pointer** alternative (unless essential).

**What we have today (CU bird’s-eye / overview map)**

| Gesture | Input | Single-pointer alternative? |
|---------|--------|------------------------------|
| **Pinch zoom** | Two fingers on stream | **No** on touch — main gap |
| **Wheel zoom** | Mouse wheel on `#remote-video` | **Yes** on desktop (`birdEyeZoomLevel` in `useRemoteVideoPointerGestures.ts`) |
| **Twist rotate map** | Two-finger angle | **No** on touch |
| **Rotate map** | Middle-mouse drag or Shift + left-drag | **Yes** on desktop only |
| **Drag pan** | One finger / one mouse button | **Yes** (already single-pointer) |

**Cannot reach Yes for 2.5.1 on mobile/touch** until design ships visible controls. Engineering will **not** add unapproved UI (project policy).

**Design ask (minimum for pinch zoom — per product discussion)**

- **Placement:** Bottom of bird’s-eye view (e.g. bottom-centre or bottom-right), above safe-area; must not block route panel / POI sheets (see `bird-eye-map-controls.mdc` inert backdrop rules).
- **Controls:** **Zoom out (−)** and **Zoom in (+)** buttons (44×44 px min touch target each).
- **Optional follow-up:** Map **rotate left / rotate right** (or compass reset) if twist must be supported on touch without middle-mouse.
- **Visual:** Match CU chrome (Lexend, purple/off-white tokens); icons + `aria-label` text supplied via i18n after copy is approved.
- **States:** Default, pressed, `:focus-visible` ring (lemon/dark purple per CU).

**After design approval — engineering (Round C)**

1. Mount control in CU view layer (e.g. near stream overlay when `currentCamera === 'bird_eye'`).
2. Wire clicks to existing `sendMessage('birdEyeZoomLevel', { level })` (same API as wheel/pinch — `useRemoteVideoPointerGestures.ts`).
3. Keyboard: buttons focusable; optional `+` / `−` shortcuts only if design/product approves (not required for 2.5.1 if buttons exist).
4. Update checklist **2.5.1** → **Yes** after QA on touch + desktop.

**References:** `.cursor/rules/topics/bird-eye-map-controls.mdc`, `.cursor/rules/topics/bird-eye-pin-anywhere.mdc`, `web-viewer-sample-main/src/features/streaming/useRemoteVideoPointerGestures.ts`

---

## Regression watch (stay Yes only if still true)

| Criterion | When to re-check |
|-----------|------------------|
| **2.3.1** Three flashes | New stadium lights, particles, weather, video, or post-processing — verify flash rate before release |
| **1.4.2** Audio control | New autoplay ambient/stream audio without user control |
| **2.2.2** Pause, stop, hide | New auto-playing motion (ads, loops, HUD) without pause/dismiss |

---

## Round E — Media / content (All / Our Normal)

| Criterion | Work |
|-----------|------|
| 1.2.2, 1.2.3, 1.2.5 | Captions, audio description, media alternatives for prerecorded video |
| 1.2.1 | Audio-only / video-only alternatives |

---

## Checklist hygiene

- **Evaluated = Partial** → audited, gaps documented in Comments column (includes **design-gated** items: interim code may exist, **Yes** waits on Kokokaka).
- **Evaluated = Yes** → conformant for CU scope tested.
- **Evaluated = No** → not started or design-owned.
- **1.3.5 seat fields** → Partial is expected: no HTML `autocomplete` token for stadium section/row/seat; we use `name` + labels.

Update `Checklist.WCAG2.2(WCAG 2.csv` Comments when a round closes; link row to PR or test notes if needed.
