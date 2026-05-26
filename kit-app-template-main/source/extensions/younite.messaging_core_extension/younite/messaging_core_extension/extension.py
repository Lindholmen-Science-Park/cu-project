import omni.ext

from .message_utils import register_outbound_events
from .services.kit_services.messaging_bridge_service import IncomingMessageBridge


class MessagingCoreExtension(omni.ext.IExt):
    """
    Starts the inbound wrapper-message bridge and registers outbound event types early,
    so other extensions can safely dispatch events before the stage opens.

    Diagnostics: use print() (carb logs not reliably visible).
    """

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id

        # Register outbound event types before any other extension dispatches them
        outbound_events = [
            # Scene lifecycle
            "scene.loaded",
            "scene.loading",
            # Loading phase (step-by-step for client UI and debugging)
            "loading.phase",
            # Stage loading/progress
            "openedStageResult",
            "updateProgressAmount",
            "updateProgressActivity",
            "loadingStateResponse",
            # Misc responses used by legacy UI/features (safe to register even if unused)
            "getChildrenResponse",
            "makePrimsPickableResponse",
            "resetStageResponse",
            "cameraViewSwitchResponse",
            "viewTransitionReady",
            "fixedCameraStatus",
            # Ack from CameraService.enter_xform_view; spatial-sound +
            # 360°-video overlays gate their mount on this so the
            # overlay never paints before the WebRTC frame at the new
            # pose lands.
            "xformViewCameraReady",
            "physicsControlResponse",
            "movementSpeedChangeResponse",
            "cameraHeightChangeResponse",
            "changeResolutionConfirmation",
            # AI chat (Ollama / dev)
            "ai.chat.response",
            "ai.chat.typing",
            "ai.chat.done",
            # AI agent (avatar chat -> external API)
            "ai.agent.response",
            "ai.agent.typing",
            "ai.agent.done",
            "ai.agent.error",
            # NavMesh route status
            "navmeshRouteStatus",
            # NavMesh route measure (distance / estimated time for web UI)
            "navmeshRouteMeasure",
            # Turn-by-turn navigation guide (derived from route polyline; seat/exit/POI routes)
            "navmeshRouteGuide",
            # NavMesh route arrival (player walked to destination without auto-move)
            "navmeshRouteArrival",
            # Routes from player to exits (for exit widget)
            "navmeshRoutesToExitsResult",
            # Routes from player to generic POIs (restrooms, etc.)
            "navmeshRoutesToPoisResult",
            # NavMesh mode change status (wheelchair / walking rebake progress)
            "navmeshModeStatus",
            # Auto-move status (arrival / cancellation notifications for web UI)
            "autoMoveStatus",
            # Camera data visualization
            "cameraDataVisualizationStatus",
            "cameraDataVisualizationStats",
            "cameraDataVisualizationHeatmapStatus",
            "cameraDataVisualizationTrackerStatus",
            # Camera data calc (navmesh integration)
            "cameraDataCalcStatus",
            # Crowd toggle status (drives traffic + seated crowd visibility)
            "peopleToggleStatus",
            # Seated crowd density variant (none / sparse / medium / dense / full)
            "seatedCrowdLayoutChanged",
            # Light culling toggle
            "lightCullingToggleStatus",
            # Tile management toggle
            "tileCullingToggleStatus",
            # Unified interaction points
            "interactionPointsSync",
            "interactionPointTriggered",
            # Incident creator (add incident -> rebake NavMesh)
            "incidentAdded",
            "incidentRemoved",
            # Maintenance bots
            "maintenanceBotStatus",
            "maintenanceBotIncidentUpdate",
            # Sound areas
            "soundLocationsSync",
            "soundDataCalcStatus",
            # Camera depth capture
            "cameraDepthStatus",
            # Video playback
            "videoListSync",
            "videoOpen",
            # Viewport capture
            "viewportCaptureResult",
            # Stadium LOD
            "stadiumLodResponse",
            # World state sync (full snapshot on connect + incremental on change)
            "worldStateSync",
            # Ambient sound emitters (published by sound_emitter_extension,
            # folded into worldStateSync via WorldStateSyncService).
            "soundEmittersStatus",
            # Player pose for 3D ambient audio (position + forward/up),
            # throttled and gated on the emitter list being non-empty.
            "playerPose",
            # Walking vs wheelchair NavMesh diff visibility ack (dev Scene menu)
            "accessibilityDiffStatus",
            # Full active NavMesh debug overlay ack (dev Scene menu)
            "navmeshDebugStatus",
            # Seat directions (bird-eye seat navigation flow)
            "seatDirectionsResolved",
            # Seat teleport preflight from bird-eye (validate before fade)
            "seatTeleportFromBirdEyeCheckResult",
            # Dev-only media CMS (web admin panel)
            "devMediaRegistryResponse",
            "devLocaleJsonWriteResult",
            # Live GTFS-RT transit overlay (dev kit)
            "transitLiveOverlayStatus",
        ]
        try:
            register_outbound_events(outbound_events)
            print("[messaging_core] outbound events registered")
        except Exception as e:
            print(f"[messaging_core] outbound registration failed: {e}")

        # Start wrapper-event -> semantic event bridge
        try:
            self._incoming_bridge = IncomingMessageBridge()
            self._incoming_bridge.start()
            print("[messaging_core] incoming message bridge started")
        except Exception as e:
            self._incoming_bridge = None
            print(f"[messaging_core] incoming bridge start failed: {e}")

    def on_shutdown(self):
        try:
            if getattr(self, "_incoming_bridge", None):
                self._incoming_bridge.stop()
        except Exception:
            pass
        self._incoming_bridge = None

