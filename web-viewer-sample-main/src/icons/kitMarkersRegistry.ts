/**
 * Kit-driven map marker icons (`interactions.json` `ui.icon` uses these basenames).
 * Do not rename files here without updating Kit config.
 */
export const kitMarkerIconUrlByBasename: Record<string, string> = (() => {
    const out: Record<string, string> = {};
    const modules = import.meta.glob('./map-markers/*.svg', {
        eager: true,
        import: 'default',
    }) as Record<string, string>;
    for (const [path, url] of Object.entries(modules)) {
        const filename = path.split('/').pop();
        if (filename) out[filename] = url;
    }
    return out;
})();
