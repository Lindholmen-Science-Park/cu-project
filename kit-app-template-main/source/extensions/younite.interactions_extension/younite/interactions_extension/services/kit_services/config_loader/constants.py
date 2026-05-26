"""Constants for ``interactions.json`` parsing and iconGroup media indexing."""

# Kit-only npcConfig keys (paths / collider / spawn tuning) — stripped from web payloads.
NPC_KIT_ONLY_KEYS = frozenset({
    "avatarAsset",
    "collider",
    "npcSpawnMeters",
    "spawnPointPrimName",
    "skipNpcSpawn",
    "npcSpawnForwardLocalZ",
})

# Extensions recognised when indexing iconGroup media folders.
_MEDIA_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".mp4", ".webm", ".mov", ".m4v"}
_CAPTION_EXTS = {".vtt"}

# Hardcoded fallbacks for env-var-driven `iconConfig` paths when the variable is unset.
ENV_FALLBACKS = {
    "NUCLEUS_SPATIAL_SOUNDS_FOLDER": "nucleus/sounds/spatial/",
}
