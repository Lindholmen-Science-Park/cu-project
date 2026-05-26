import carb


class FogService:
    """Controls RTX Fog via carb.settings."""

    def set_fog(self, *, enabled: bool, intensity: float):
        settings = carb.settings.get_settings()

        try:
            if intensity is None:
                intensity = 0.0
            intensity = max(0.0, min(1.0, float(intensity)))
        except Exception:
            intensity = 0.0

        try:
            settings.set("/rtx/fog/enabled", bool(enabled))
            settings.set("/rtx/fog/fogColorIntensity", float(intensity))
        except Exception:
            pass

