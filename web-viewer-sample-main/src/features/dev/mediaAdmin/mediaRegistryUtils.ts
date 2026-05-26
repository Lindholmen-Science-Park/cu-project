import type { InteractionPointDef } from '../../streaming/types';

export const LOCALES = ['en', 'sv', 'fr', 'es'] as const;
export type LocaleCode = (typeof LOCALES)[number];

export const VIDEO360_I18N_FIELDS = ['greeting', 'title', 'subtitle', 'videoTitle'] as const;
export const SPATIAL_I18N_FIELDS = ['greeting', 'title', 'subtitle', 'soundTitle'] as const;

/** `1_foo.mp4` → `1` */
export function numericPrefixFromMediaFilename(name: string): string | null {
    const m = name.match(/^(\d+)_/);
    return m ? m[1] : null;
}

/** Same convention as Kit ``_extract_number_prefix`` (``video_360_12`` → ``12``). */
export function numericPrefixFromPrimName(leafName: string): string | null {
    let m = leafName.match(/_(\d+)$/);
    if (!m) m = leafName.match(/(\d+)$/);
    return m ? m[1] : null;
}

export interface KitRegistryItem {
    pattern: string;
    primPath: string;
    primName: string;
    worldTranslate: [number, number, number] | null;
}

export interface Video360RowModel {
    kind: 'video360';
    numericId: string;
    mediaFiles: string[];
    primNames: string[];
    kitPositions: { primName: string; xyz: [number, number, number] }[];
    expandedInSession: boolean;
    interactionBaseId: string | null;
    videoUrl: string | null;
    i18nKeys: Record<LocaleCode, Record<string, string | undefined>>;
    missingI18n: { locale: LocaleCode; field: string }[];
    gaps: string[];
}

export interface SpatialSoundRowModel {
    kind: 'spatialSound';
    numericId: string;
    mediaFiles: string[];
    primNames: string[];
    kitPositions: { primName: string; xyz: [number, number, number] }[];
    expandedInSession: boolean;
    interactionBaseId: string | null;
    soundUrl: string | null;
    i18nKeys: Record<LocaleCode, Record<string, string | undefined>>;
    missingI18n: { locale: LocaleCode; field: string }[];
    gaps: string[];
}

function collectVideo360FromInteractions(
    defs: InteractionPointDef[],
): Map<string, { id: string; videoUrl?: string }> {
    const byNum = new Map<string, { id: string; videoUrl?: string }>();
    for (const d of defs) {
        const id = d.id || '';
        const m = id.match(/^icon_video_360_(\d+)$/);
        if (!m) continue;
        const num = m[1];
        const ic = (d as unknown as { iconConfig?: { videoUrl?: string; mediaType?: string } }).iconConfig;
        const videoUrl = ic?.videoUrl ? String(ic.videoUrl) : undefined;
        byNum.set(num, { id, videoUrl });
    }
    return byNum;
}

function collectSpatialFromInteractions(
    defs: InteractionPointDef[],
): Map<string, { id: string; soundUrl?: string }> {
    const byNum = new Map<string, { id: string; soundUrl?: string }>();
    for (const d of defs) {
        const id = d.id || '';
        const m = id.match(/^icon_spatial_sound_(\d+)$/);
        if (!m) continue;
        const num = m[1];
        const ic = (d as unknown as { iconConfig?: { soundUrl?: string; mediaType?: string } }).iconConfig;
        const soundUrl = ic?.soundUrl ? String(ic.soundUrl) : undefined;
        byNum.set(num, { id, soundUrl });
    }
    return byNum;
}

function indexKitByNumericId(
    items: KitRegistryItem[] | null | undefined,
    pattern: string,
): Map<string, KitRegistryItem[]> {
    const map = new Map<string, KitRegistryItem[]>();
    if (!items?.length) return map;
    for (const it of items) {
        if (it.pattern !== pattern) continue;
        const n = numericPrefixFromPrimName(it.primName);
        if (!n) continue;
        const arr = map.get(n) || [];
        arr.push(it);
        map.set(n, arr);
    }
    return map;
}

function readI18nField(
    bundles: Record<LocaleCode, Record<string, unknown>>,
    baseKey: string,
    field: string,
    locale: LocaleCode,
): string | undefined {
    const interactions = bundles[locale]?.interactions as Record<string, unknown> | undefined;
    const block = interactions?.[baseKey] as Record<string, string> | undefined;
    const v = block?.[field];
    return typeof v === 'string' ? v : undefined;
}

function collectMissingI18n(
    bundles: Record<LocaleCode, Record<string, unknown>>,
    baseKey: string,
    fields: readonly string[],
): { locale: LocaleCode; field: string }[] {
    const miss: { locale: LocaleCode; field: string }[] = [];
    for (const loc of LOCALES) {
        for (const f of fields) {
            const v = readI18nField(bundles, baseKey, f, loc);
            if (v === undefined || v.trim() === '') miss.push({ locale: loc, field: f });
        }
    }
    return miss;
}

export function buildVideo360Rows(
    defs: InteractionPointDef[],
    videoFilenames: string[],
    kitItems: KitRegistryItem[] | null,
    bundles: Record<LocaleCode, Record<string, unknown>>,
): Video360RowModel[] {
    const fromMedia = new Map<string, string[]>();
    for (const f of videoFilenames) {
        const n = numericPrefixFromMediaFilename(f);
        if (!n) continue;
        const arr = fromMedia.get(n) || [];
        arr.push(f);
        fromMedia.set(n, arr);
    }

    const fromKit = indexKitByNumericId(kitItems, 'video_360_*');
    const fromIx = collectVideo360FromInteractions(defs);

    const ids = new Set<string>([...fromMedia.keys(), ...fromKit.keys(), ...fromIx.keys()]);

    const rows: Video360RowModel[] = [];
    for (const numericId of [...ids].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))) {
        const mediaFiles = fromMedia.get(numericId) || [];
        const kitList = fromKit.get(numericId) || [];
        const primNames = [...new Set(kitList.map((k) => k.primName))];
        const kitPositions = kitList
            .filter((k) => k.worldTranslate)
            .map((k) => ({ primName: k.primName, xyz: k.worldTranslate! }));

        const ix = fromIx.get(numericId);
        const interactionBaseId = ix?.id || null;
        const videoUrl = ix?.videoUrl || null;
        const expandedInSession = !!ix;

        const baseKey = `icon_video_360_${numericId}`;
        const i18nKeys = {} as Video360RowModel['i18nKeys'];
        for (const loc of LOCALES) {
            i18nKeys[loc] = {};
            for (const f of VIDEO360_I18N_FIELDS) {
                i18nKeys[loc][f] = readI18nField(bundles, baseKey, f, loc);
            }
        }
        const missingI18n = collectMissingI18n(bundles, baseKey, VIDEO360_I18N_FIELDS);

        const gaps: string[] = [];
        if (mediaFiles.length === 0) gaps.push('no video file (NN_*.mp4)');
        if (primNames.length === 0) gaps.push('no Xform under /World');
        if (!expandedInSession) gaps.push('not expanded (need both video + Xform for this index)');
        if (missingI18n.length > 0) gaps.push(`i18n incomplete (${missingI18n.length} missing)`);

        rows.push({
            kind: 'video360',
            numericId,
            mediaFiles,
            primNames,
            kitPositions,
            expandedInSession,
            interactionBaseId,
            videoUrl,
            i18nKeys,
            missingI18n,
            gaps,
        });
    }
    return rows;
}

export function buildSpatialSoundRows(
    defs: InteractionPointDef[],
    soundFilenames: string[],
    kitItems: KitRegistryItem[] | null,
    bundles: Record<LocaleCode, Record<string, unknown>>,
): SpatialSoundRowModel[] {
    const fromMedia = new Map<string, string[]>();
    for (const f of soundFilenames) {
        const n = numericPrefixFromMediaFilename(f);
        if (!n) continue;
        const arr = fromMedia.get(n) || [];
        arr.push(f);
        fromMedia.set(n, arr);
    }

    const fromKit = indexKitByNumericId(kitItems, 'spatial_sound_*');
    const fromIx = collectSpatialFromInteractions(defs);

    const ids = new Set<string>([...fromMedia.keys(), ...fromKit.keys(), ...fromIx.keys()]);

    const rows: SpatialSoundRowModel[] = [];
    for (const numericId of [...ids].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))) {
        const mediaFiles = fromMedia.get(numericId) || [];
        const kitList = fromKit.get(numericId) || [];
        const primNames = [...new Set(kitList.map((k) => k.primName))];
        const kitPositions = kitList
            .filter((k) => k.worldTranslate)
            .map((k) => ({ primName: k.primName, xyz: k.worldTranslate! }));

        const ix = fromIx.get(numericId);
        const interactionBaseId = ix?.id || null;
        const soundUrl = ix?.soundUrl || null;
        const expandedInSession = !!ix;

        const baseKey = `icon_spatial_sound_${numericId}`;
        const i18nKeys = {} as SpatialSoundRowModel['i18nKeys'];
        for (const loc of LOCALES) {
            i18nKeys[loc] = {};
            for (const f of SPATIAL_I18N_FIELDS) {
                i18nKeys[loc][f] = readI18nField(bundles, baseKey, f, loc);
            }
        }
        const missingI18n = collectMissingI18n(bundles, baseKey, SPATIAL_I18N_FIELDS);

        const gaps: string[] = [];
        if (mediaFiles.length === 0) gaps.push('no sound file (NN_*.wav/mp3)');
        if (primNames.length === 0) gaps.push('no Xform under /World');
        if (!expandedInSession) gaps.push('not expanded (need both sound + Xform)');
        if (missingI18n.length > 0) gaps.push(`i18n incomplete (${missingI18n.length} missing)`);

        rows.push({
            kind: 'spatialSound',
            numericId,
            mediaFiles,
            primNames,
            kitPositions,
            expandedInSession,
            interactionBaseId,
            soundUrl,
            i18nKeys,
            missingI18n,
            gaps,
        });
    }
    return rows;
}

export function videoFilenamesFromGlob(): string[] {
    const raw = import.meta.glob('@nucleus-videos/*.{mp4,webm,mov}', { eager: true, import: 'default' }) as Record<
        string,
        string
    >;
    return Object.keys(raw)
        .map((p) => p.split('/').pop() || '')
        .filter(Boolean);
}

export function soundFilenamesFromGlob(): string[] {
    const raw = import.meta.glob('@nucleus-sounds/**/*.{wav,mp3,ogg,flac}', {
        eager: true,
        import: 'default',
    }) as Record<string, string>;
    return Object.keys(raw)
        .map((p) => p.split('/').pop() || '')
        .filter(Boolean);
}
