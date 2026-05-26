# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# Copied from the old monolithic implementation (keep behavior).

import asyncio
import os

import carb
import carb.events
import carb.tokens

import omni.kit.app
import omni.usd


class LoadingManager:
    """Manages the loading of USD stages and sends messages to the client"""

    def __init__(self):
        self._subscriptions = []  # Holds subscription pointers

        # -- state variables
        # URL of stage load request. Can be used in messaging with client.
        self._requested_stage_url: str = ""
        self._stage_is_opening: bool = False

        # URL of loaded stage. Should not be used in messaging with client
        # because it may reveal directory paths in environment where
        # application runs.
        self._opened_stage_url: str = ""
        self._stage_has_opened = False
        self._streaming_manager_is_busy: bool = False

        # States if opened stage is opened from storage as in not a
        # new unsaved stage
        self._persisted_stage: bool = False
        self._is_evaluating_loading_status: bool = False
        self._webrtc_connected: bool = False  # Track WebRTC connection state

        # -- register outgoing events/messages
        outgoing = [
            "openedStageResult",  # notify when USD Stage has loaded.
            "updateProgressAmount",  # Status bar event denoting progress
            "updateProgressActivity",  # Status bar event denoting activity
            "loadingStateResponse",  # Response to loadingStateQuery
        ]

        # Modern WebRTC messaging - no need to register with deprecated messaging extension
        print("[stage_core] Using livestream messaging outbound registration from messaging_core")

        # -- register incoming events/messages
        incoming = {
            'openStageRequest': self._on_open_stage,  # request to open a stage
            # internal event to capture progress status
            "omni.kit.window.status_bar@progress": self._on_progress,
            # internal event to capture progress activity
            "omni.kit.window.status_bar@activity": self._on_activity,
            "loadingStateQuery": self._on_load_state_query,
        }

        import omni.kit.app
        # Use Events 2.0 API - proper event dispatcher usage
        ed = carb.eventdispatcher.get_eventdispatcher()

        for event_type, handler in incoming.items():
            # Register event aliases for Events 2.0 compatibility
            event_type_id = carb.events.type_from_string(event_type)
            omni.kit.app.register_event_alias(event_type_id, event_type)

            # Use Events 2.0 observer instead of deprecated subscription
            observer = ed.observe_event(
                observer_name=f"younite.usd_viewer_stage_core_extension/stage_loading/{event_type}",
                event_name=event_type,
                on_event=handler,
                order=0,
            )
            self._subscriptions.append(observer)

        # -- subscribe to stage events using Events 2.0
        ed = carb.eventdispatcher.get_eventdispatcher()
        stage_observer = ed.observe_event(
            observer_name="younite.usd_viewer_stage_core_extension/stage_loading/stage_events",
            event_name="omni.usd@stage_event",
            on_event=self._on_stage_event,
            order=0,
        )
        self._subscriptions.append(stage_observer)

        # -- subscribe to WebRTC connection events
        self._setup_webrtc_connection_tracking()

    def _setup_webrtc_connection_tracking(self):
        """Setup WebRTC connection state tracking for safe messaging"""
        # Listen for WebRTC connection events
        ed = carb.eventdispatcher.get_eventdispatcher()

        # Connection established
        observer_connected = ed.observe_event(
            observer_name="younite.usd_viewer_stage_core_extension/webrtc_connected",
            event_name="omni.kit.livestream@connected",
            on_event=self._on_webrtc_connected,
            order=0,
        )
        self._subscriptions.append(observer_connected)

        # Connection lost
        observer_disconnected = ed.observe_event(
            observer_name="younite.usd_viewer_stage_core_extension/webrtc_disconnected",
            event_name="omni.kit.livestream@disconnected",
            on_event=self._on_webrtc_disconnected,
            order=0,
        )
        self._subscriptions.append(observer_disconnected)

    def _on_webrtc_connected(self, event):
        """Handle WebRTC connection established"""
        self._webrtc_connected = True
        print("[stage_core] WebRTC connection established - messaging enabled")

    def _on_webrtc_disconnected(self, event):
        """Handle WebRTC connection lost"""
        self._webrtc_connected = False
        print("[stage_core] WebRTC connection lost - messaging disabled")

        # -- subscribe to RTX streaming status events using Events 2.0
        # This provides better streaming status tracking when available
        try:
            ed = carb.eventdispatcher.get_eventdispatcher()
            rtx_observer = ed.observe_event(
                observer_name="younite.usd_viewer_stage_core_extension/rtx_streaming_status",
                event_name="omni.rtx.StreamingStatus",
                on_event=self._on_rxt_streaming_event,
                order=0,
            )
            self._subscriptions.append(rtx_observer)
            print("[stage_core] RTX streaming status events subscribed successfully")
        except Exception as e:
            print(f"[stage_core] RTX streaming status events not available: {e}")

    def _on_load_state_query(self, event: carb.events.IEvent) -> None:
        if event.type == carb.events.type_from_string("loadingStateQuery"):
            event_type_id = carb.events.type_from_string("loadingStateResponse")
            omni.kit.app.register_event_alias(event_type_id, "loadingStateResponse")
            payload = {"loading_state": "idle", "url": self._opened_stage_url}
            if self._stage_is_opening:
                payload = {"loading_state": "busy", "url": self._requested_stage_url}
            elif self._stage_has_opened:
                payload = {"loading_state": "idle", "url": self._requested_stage_url}

            self._safe_dispatch_event("loadingStateResponse", payload)

    def _on_open_stage(self, event: carb.events.IEvent) -> None:
        """
        Handler for `openStageRequest` event.

        Starts loading a given URL, will send success if the layer is already
        loaded, and an error on any failure.
        """
        if event.type == carb.events.type_from_string("openStageRequest"):

            if "url" not in event.payload:
                print(f"[stage_core] Unexpected message payload: missing url. Payload: {event.payload}")
                return

            self._requested_stage_url = event.payload["url"]
            print(f"[stage_core] Received message to load '{self._requested_stage_url}'")

            def process_url(url):
                if url.startswith(("./", ".\\")):
                    if url.startswith(("./samples", ".\\samples")):
                        sample_url = carb.tokens.acquire_tokens_interface().resolve(
                            "${omni.usd_viewer.samples}/" + url[1:].replace("samples", "samples_data")
                        )
                        if os.path.exists(sample_url):
                            return sample_url
                    return carb.tokens.acquire_tokens_interface().resolve(
                        "${app}/.." + url[1:]
                    )
                return carb.tokens.acquire_tokens_interface().resolve(url)

            url = process_url(self._requested_stage_url)

            stage = omni.usd.get_context().get_stage()
            current_stage = stage.GetRootLayer().identifier if stage else ''

            if omni.client.utils.equal_urls(url, current_stage):
                print(f"[stage_core] Client requested stage already open: {url}")
                event_type_id = carb.events.type_from_string("openedStageResult")
                omni.kit.app.register_event_alias(event_type_id, "openedStageResult")
                payload = {"url": self._requested_stage_url, "result": "success", "error": ''}
                self._safe_dispatch_event("openedStageResult", payload)
                self._reset_state()
                return

            async def open_stage():
                print(f"[stage_core] Opening stage per client request: {url}")
                usd_context = omni.usd.get_context()
                if url:
                    result, error = await usd_context.open_stage_async(url, omni.usd.UsdContextInitialLoadSet.LOAD_ALL)
                else:
                    result, error = await usd_context.new_stage_async()

                if result is not True:
                    event_type_id = carb.events.type_from_string("openedStageResult")
                    omni.kit.app.register_event_alias(event_type_id, "openedStageResult")
                    print(f"[stage_core] Stage load failed: {url} (error: {error})")
                    payload = {"url": url, "result": "error", "error": error}
                    self._safe_dispatch_event("openedStageResult", payload)
                    self._reset_state()
                    return

            asyncio.ensure_future(open_stage())

    def _on_stage_event(self, event: carb.events.IEvent) -> None:
        if event.type == int(omni.usd.StageEventType.OPENING):
            self._stage_is_opening = True
            payload: dict = event.payload.get_dict()
            if 'val' in payload.keys():
                self._opened_stage_url = payload['val']
            else:
                self._opened_stage_url = ''
            self._persisted_stage = True if self._opened_stage_url else False
            return

        if event.type == int(omni.usd.StageEventType.ASSETS_LOADED):
            if not self._stage_is_opening:
                return
            self._stage_is_opening = False
            self._stage_has_opened = True
            asyncio.ensure_future(self._evaluate_load_status())
            return

    def _on_rxt_streaming_event(self, event: carb.events.IEvent) -> None:
        self._streaming_manager_is_busy = event.payload['isBusy']

    async def _evaluate_load_status(self):
        if not self._persisted_stage:
            return
        if self._is_evaluating_loading_status:
            return
        self._is_evaluating_loading_status = True

        while self._streaming_manager_is_busy or not self._stage_has_opened:
            await omni.kit.app.get_app().next_update_async()

        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()

        event_type_id = carb.events.type_from_string("openedStageResult")
        omni.kit.app.register_event_alias(event_type_id, "openedStageResult")
        url = self._requested_stage_url if self._requested_stage_url else '[obfuscated]'
        print(f"[stage_core] Sending openedStageResult success: {url}")
        payload = {"url": url, "result": "success", "error": ''}
        self._safe_dispatch_event("openedStageResult", payload)

        self._is_evaluating_loading_status = False
        self._reset_state()

    def _on_progress(self, event):
        if not self._persisted_stage:
            return
        event_type_id = carb.events.type_from_string("updateProgressAmount")
        omni.kit.app.register_event_alias(event_type_id, "updateProgressAmount")
        payload = event.payload if hasattr(event, 'payload') else {}
        self._safe_dispatch_event("updateProgressAmount", payload)

    def _on_activity(self, event):
        if not self._persisted_stage:
            return
        event_type_id = carb.events.type_from_string("updateProgressActivity")
        omni.kit.app.register_event_alias(event_type_id, "updateProgressActivity")
        payload = event.payload if hasattr(event, 'payload') else {}
        self._safe_dispatch_event("updateProgressActivity", payload)

    def _safe_dispatch_event(self, event_name, payload):
        ed = carb.eventdispatcher.get_eventdispatcher()
        ed.dispatch_event(event_name, payload)

    def on_shutdown(self) -> None:
        if self._subscriptions:
            self._subscriptions.clear()

    def _reset_state(self):
        stage = omni.usd.get_context().get_stage()
        self._requested_stage_url = ""
        self._opened_stage_url = stage.GetRootLayer().identifier if stage else ""
        self._stage_has_opened = False
        self._streaming_manager_is_busy = False
        self._persisted_stage = False

