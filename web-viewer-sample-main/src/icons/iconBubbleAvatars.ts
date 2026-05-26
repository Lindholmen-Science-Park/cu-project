/**
 * Proximity bubble avatars resolved by basename (`interactions.iconConfig` filenames).
 *
 * Looks up `*_avatar.{svg,png,jpg,webp}` under `map-markers/` (NPCs, video book,
 * spatial sound, 360° video icons) and `*.svg` under `Coins/` (POI coin
 * round-sign icons — see `poi-coins.mdc`).
 */
const iconBubbleAvatarModules = import.meta.glob('./map-markers/*_avatar.{svg,png,jpg,webp}', {
    eager: true,
    import: 'default',
}) as Record<string, string>;

const coinIconModules = import.meta.glob('./Coins/*.svg', {
    eager: true,
    import: 'default',
}) as Record<string, string>;

export function resolveIconBubbleAvatarUrl(filename: string): string | null {
    for (const [path, url] of Object.entries(iconBubbleAvatarModules)) {
        if (path.endsWith(`/${filename}`)) return url;
    }
    for (const [path, url] of Object.entries(coinIconModules)) {
        if (path.endsWith(`/${filename}`)) return url;
    }
    return null;
}
