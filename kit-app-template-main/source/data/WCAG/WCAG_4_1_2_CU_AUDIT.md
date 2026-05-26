# WCAG 4.1.2 — CU frontend systematic audit

**Date:** 2026-05-26  
**Criterion:** [4.1.2 Name, Role, Value](https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html) (Level A)  
**Checklist:** `Partial` — use this file to track gaps before claiming **Yes**.

**Scope:** Production CU (`features/cu/**`, `CuViewLayer`, CU-visible `streaming/` overlays/widgets). **Out of scope:** `features/dev/**` unless noted as “dev-only”.

---

## Summary

| Bucket | Count | Notes |
|--------|------:|-------|
| **OK (no change)** | Majority | Native controls, visible labels, or fixed in Round C passes |
| **Minor fixes applied** | 5 | See “Fixed in this audit” |
| **Open — CU** | 0 | Polish rows 1–3 resolved or excluded (see below) |
| **Open — dev / debug only** | 7 | Includes legacy `ChatWidget` (Ollama); not required for CU sign-off |
| **Out of scope (other criteria)** | 1 | WebRTC focus (2.4.3) |

---

## Fixed in earlier Round C passes

- Controls menu search chips, explore/settings/dev actions, hamburger/people/view toggle
- Immersive media: `MediaPlayerControls`, videobook / 360° / spatial sound players
- Flat video modal (`VideoPlayerOverlay`) — play/pause label-only
- Interaction overlays: map pins, speech bubbles, video trigger
- Seat avoidance toggles, route recalculate icon
- `PanelCloseButton` default `title`
- Spatial sound close (`controlsTimerRef` bug)

---

## Fixed in this audit (CU)

| File | Change |
|------|--------|
| `ChatWidget.tsx` | Dev-only widget hygiene: close `type="button"`; send `aria-label` (not a CU product surface) |
| `SeatFormBody.tsx` | CU teleport: `aria-label` (was `title` only) |
| `AppStreamSeatOverlays.tsx` | Route-bar mute: `aria-pressed` |
| `VideoBookOverlay.tsx` | Splash chip button: correct settings `aria-label` (was `peopleGroups`) |
| `NpcBubbleOverlay.tsx` | Open chat: `aria-label={t('avatar.openChatWithGuide')}` |

---

## Accepted / resolved polish (2026-05-26)

### 1. Immersive media — tap-to-show-chrome (**accepted, no code change**)

**Surfaces:** `VideoBookPlayer` (`vbp-video-area`), `Video360Overlay` (sphere), `SpatialSoundOverlay` (visualization).

**Behaviour:** Pointer tap on the video/sphere/visualization only calls `resetControlsTimer()` so auto-hidden transport chrome reappears. Play/pause, mute, captions, seek, close, etc. remain separate `<button>` elements with `aria-label` / `aria-pressed`.

**4.1.2 rationale:** The tap target is a **non-control pointer affordance** (same pattern as tap-to-reveal controls on many video players). It does not need `role`, `aria-label`, or tab focus because it is not a discrete user action in the accessibility tree.

**Keyboard / SR path:** `useControlsAutoHide` keeps chrome visible while focus is inside the chrome root (`focusPinned` + `onChromeFocusCapture`). Keyboard users reach labeled controls even when chrome is visually faded; no sr-only “Show controls” button required.

**QA note:** Spot-check Tab through videobook / 360° / spatial with chrome hidden; confirm play, close, and seek stay focusable and named.

### 2. Globe Cesium pins — **excluded (dev-only)**

**Surface:** `GlobeViewOverlay` / `GlobeLocationPin` — `Entity` `onClick` on the Cesium canvas.

**Not in CU scope:** Globe (`currentCamera === 'space'`) is mounted only when `appMode === 'dev'` (`StreamOnlyWindow.tsx`). Public CU visitors never see it. Do **not** block CU checklist **4.1.2 Yes** on pin accessibility.

**If dev globe is improved later:** Add a parallel HTML list of `globe-locations.json` entries as `<button>`s (keyboard + SR), or document as a canvas/map exception. Back button and `globe.clickPinHint` already exist for pointer users.

### 3. NPC bubble open chat — **fixed**

**Surface:** `NpcBubbleOverlay.tsx` — `npc-bubble-open` button.

**Change:** `aria-label={t('avatar.openChatWithGuide')}` so screen readers get a clear action name; visible greeting text unchanged for sighted users.

---

## Open gaps — dev / debug only (exclude from CU Yes)

| Location | Issue |
|----------|--------|
| `ChatWidget.tsx` | **Legacy Ollama UI** (`younite.ai_chat_extension` / `ai.chat.*`) — still mounted in the stream shell but **not** production CU chat (`AvatarChatOverlay` + `ai.agent.*`). Move CTA (“Do you want me to take you there?” + Yes/No) is hardcoded English; **no CU CTA product yet** — do not track as a CU 4.1.2 or i18n gap. Localize or remove only if `ai_chat_extension` is revived. |
| `PlacementButtons.tsx` | Shown when dev placement modes enabled; inline English; some toggles lack `aria-pressed` |
| `PoiRoutesWidget.tsx` | Icon-only close/refresh; list rows are `<li onClick>` not buttons |
| `OsmNavigateWidget.tsx` | Dev-opened; mixed English |
| `SoundCostWidget.tsx`, `CameraPathfindingWidget.tsx` | Icon close without `aria-label`; dev panels |
| `InteractionButtons.tsx` | Legacy test UI; weather/camera buttons lack `aria-pressed` |
| IoT panels (`IotAirStationsPanel`, etc.) | **Dev-only** extension; metric tabs have visible text + `aria-pressed` — acceptable for dev |

---

## Verified OK (representative)

| Area | Pattern |
|------|---------|
| `CUControls` | Icon buttons: `aria-label`, `aria-expanded` / `aria-pressed` |
| `ControlsMenu` / search | Chips, mic, send, assistant strip |
| `SettingsPanel` / `PeoplePanel` | Dialog, tabs, switches (`role=switch`, `aria-checked`) |
| `LanguageDropdown` / `EventDropdown` | Combobox + `role=listbox` / `option` |
| `PreferencesGrids` / `World3dSettings` | `role=radio` + `aria-checked` |
| `WeatherSeasonPicker` | `aria-pressed` + `aria-label` |
| `OnboardingOverlay` | Tabs + CTA with visible label |
| `PoiInfoCard`, map sheets, directions panel | Dialogs, labeled buttons |
| `RestroomWidget` / `QuietZoneWidget` | Close, filters, cards |
| `SeatChoiceDropdown`, `CuBottomSheet` tabs | Listbox / tab pattern |
| `AvatarChatOverlay` | Labeled controls, TTS `aria-pressed` |
| `IconBubbleOverlay`, `WelcomeAvatarOverlay` | `aria-label` on pill/avatar |
| `TriggerZoneToast`, `SpectatorJoinGate` | Close label / visible CTA text |
| `VideoBookOverlay` chapters | Visible `ch.label` on buttons |
| IoT list rows (dev) | `aria-pressed` on selection |

---

## Related criteria (not 4.1.2)

| Criterion | Note |
|-----------|------|
| **2.4.3 Focus order** | WebRTC `#remote-video` vs chrome tab order — separate Round C item |
| **1.1.1** | Icon `alt=""` with parent name — separate checklist row |

**CU chat / move CTA:** Production NPC + search chat is `AvatarChatOverlay` (`ai.agent.*`). No CU “take me there” CTA in product today; future agent suggestions would be designed + localized separately (see `ai-agent.mdc`).

---

## Path to checklist **Yes**

1. Product accepts **dev-only** widgets (and dev-only globe) staying unaudited for CU sign-off.  
2. Short QA pass: Tab through CU flows (onboarding → controls → seat → restroom → videobook/360/spatial) with screen reader; confirm immersive chrome focus when faded (see §1 accepted).  
3. Update `Checklist.WCAG2.2(WCAG 2.csv` row 4.1.2 to **Yes** with comment referencing this file + date.
