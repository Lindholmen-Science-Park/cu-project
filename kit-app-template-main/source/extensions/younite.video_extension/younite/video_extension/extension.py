"""
Video playback extension — manages a catalog of pre-rendered videos
and serves metadata to the web frontend via messaging.

The extension holds the video registry (hardcoded for now, JSON-driven later)
and responds to frontend requests with video metadata including source URLs.
Videos are played client-side; the stream continues running underneath.

Videobook data is managed via interactions.json (iconConfig) and flows
through the interactions extension — no separate catalog needed here.
"""

import omni.ext


# Default video catalog — replace with JSON file or DB lookup later
_DEFAULT_VIDEOS = [
    {
        "id": "test_video_01",
        "title": "Welcome to the Arena",
        "description": "A short introduction to the venue and its facilities.",
        "source": "test_video.mp4",
        "durationSeconds": 30,
    },
]


class VideoExtension(omni.ext.IExt):
    """
    Manages pre-rendered video catalog and messaging contracts.

    Inbound events (web -> Kit):
      - videoListRequest  — frontend asks for the available video list
      - videoPlaybackEvent — frontend notifies Kit about playback state
                             (started, paused, ended) for analytics / future actions

    Outbound events (Kit -> web):
      - videoListSync  — sends the full video catalog to the frontend
      - videoOpen      — tells the frontend to open a specific video
                         (used by trigger boxes / interactions in the future)
    """

    OUTBOUND_EVENTS = [
        "videoListSync",
        "videoOpen",
    ]

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._videos = list(_DEFAULT_VIDEOS)

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
                dispatch_to_events2,
                register_outbound_events,
            )

            register_outbound_events(self.OUTBOUND_EVENTS)

            ed = carb.eventdispatcher.get_eventdispatcher()

            for evt_name in ("videoListRequest", "videoPlaybackEvent"):
                try:
                    kit_app.register_event_alias(
                        carb.events.type_from_string(evt_name), evt_name,
                    )
                except Exception:
                    pass

            def _on_list_request(evt):
                dispatch_to_events2("videoListSync", {"videos": self._videos})

            def _on_playback_event(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                video_id = payload.get("videoId", "")
                action = payload.get("action", "")
                print(f"[video] playback event: id={video_id} action={action}")

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.video_extension/videoListRequest",
                    event_name="videoListRequest",
                    on_event=_on_list_request,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.video_extension/videoPlaybackEvent",
                    event_name="videoPlaybackEvent",
                    on_event=_on_playback_event,
                    order=0,
                )
            )

            print(f"[video] extension started — {len(self._videos)} video(s) in catalog")
        except Exception as e:
            print(f"[video] startup failed: {e}")

    def on_shutdown(self):
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
