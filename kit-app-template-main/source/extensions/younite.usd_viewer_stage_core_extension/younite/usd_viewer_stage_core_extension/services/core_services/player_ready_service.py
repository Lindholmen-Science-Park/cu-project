class PlayerReadyService:
    """
    Coordinates PlayerCore readiness -> stage/app readiness:
    - watches `/younite/player/ready`
    - marks stage initialized, emits `scene.loaded`
    - sets `/younite/app/ready`
    - enables non-core feature extensions
    """

    def __init__(self, *, settings, player_ready_setting: str, app_ready_setting: str, track_task_cb=None):
        self._settings = settings
        self._player_ready_setting = player_ready_setting
        self._app_ready_setting = app_ready_setting
        self._track_task = track_task_cb or (lambda t: t)

        self._sub = None

    def start(self, on_player_ready_cb):
        self._on_player_ready_cb = on_player_ready_cb
        try:
            if self._settings:
                self._sub = self._settings.subscribe_to_node_change_events(
                    self._player_ready_setting, self._on_player_ready_changed
                )
        except Exception:
            self._sub = None

        # Catch-up if PlayerCore already set ready before we subscribed (rare)
        try:
            if self._settings and bool(self._settings.get(self._player_ready_setting)):
                self._on_player_ready_cb()
        except Exception:
            pass

    def stop(self):
        self._sub = None
        self._on_player_ready_cb = None
        self._track_task = None

    def _on_player_ready_changed(self, *_args, **_kwargs):
        try:
            if self._settings and bool(self._settings.get(self._player_ready_setting)):
                if self._on_player_ready_cb:
                    self._on_player_ready_cb()
        except Exception:
            pass

