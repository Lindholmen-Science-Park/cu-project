import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useControl, useNavigation, useStream } from '../../streaming/contexts';
import { sendMessage } from '../../streaming/messaging';
import {
    LOCALES,
    SPATIAL_I18N_FIELDS,
    VIDEO360_I18N_FIELDS,
    buildSpatialSoundRows,
    buildVideo360Rows,
    soundFilenamesFromGlob,
    videoFilenamesFromGlob,
    type LocaleCode,
    type SpatialSoundRowModel,
    type Video360RowModel,
} from './mediaRegistryUtils';

import enLocale from '../../../i18n/locales/en.json';
import svLocale from '../../../i18n/locales/sv.json';
import frLocale from '../../../i18n/locales/fr.json';
import esLocale from '../../../i18n/locales/es.json';

const panelStyle: React.CSSProperties = {
    position: 'fixed',
    top: 56,
    left: 16,
    width: 'min(920px, calc(100vw - 32px))',
    maxHeight: 'calc(100vh - 80px)',
    overflow: 'auto',
    padding: 16,
    backgroundColor: 'rgba(12, 14, 20, 0.94)',
    border: '1px solid rgba(100, 180, 255, 0.35)',
    borderRadius: 12,
    color: '#e8eaef',
    fontSize: 13,
    zIndex: 1600,
    fontFamily: 'Lexend, system-ui, sans-serif',
    boxShadow: '0 8px 32px rgba(0,0,0,0.45)',
};

const btnStyle: React.CSSProperties = {
    padding: '6px 12px',
    fontSize: 12,
    fontWeight: 600,
    borderRadius: 6,
    border: '1px solid rgba(255,255,255,0.2)',
    background: 'rgba(255,255,255,0.08)',
    color: '#fff',
    cursor: 'pointer',
};

const THEMES = [
    { id: 'horseshow', label: 'Horse show' },
    { id: 'hockey', label: 'Ice hockey (future pack)' },
] as const;

const bundles: Record<LocaleCode, Record<string, unknown>> = {
    en: enLocale as Record<string, unknown>,
    sv: svLocale as Record<string, unknown>,
    fr: frLocale as Record<string, unknown>,
    es: esLocale as Record<string, unknown>,
};

function buildDraftFromRow(row: Video360RowModel | SpatialSoundRowModel): Record<LocaleCode, Record<string, string>> {
    const out = {} as Record<LocaleCode, Record<string, string>>;
    for (const loc of LOCALES) {
        out[loc] = { ...(row.i18nKeys[loc] as Record<string, string>) };
    }
    return out;
}

type DraftMap = Record<string, Record<LocaleCode, Record<string, string>>>;

const MediaAdminPanel: React.FC = () => {
    const { t } = useTranslation();
    const stream = useStream();
    const nav = useNavigation();
    const ctrl = useControl();

    const [tab, setTab] = useState<'video360' | 'spatial'>('video360');
    const [expandedRow, setExpandedRow] = useState<Video360RowModel | SpatialSoundRowModel | null>(null);
    const [draftByKey, setDraftByKey] = useState<DraftMap>({});

    const kitRegistry = ctrl.mediaAdminKitRegistry;
    const videoFiles = useMemo(() => videoFilenamesFromGlob(), []);
    const soundFiles = useMemo(() => soundFilenamesFromGlob(), []);

    const videoRows = useMemo(
        () => buildVideo360Rows(nav.interactionPointDefs, videoFiles, kitRegistry, bundles),
        [nav.interactionPointDefs, videoFiles, kitRegistry],
    );

    const spatialRows = useMemo(
        () => buildSpatialSoundRows(nav.interactionPointDefs, soundFiles, kitRegistry, bundles),
        [nav.interactionPointDefs, soundFiles, kitRegistry],
    );

    useEffect(() => {
        if (!stream.streamReady) return;
        sendMessage('devMediaRegistryRequest', {
            patterns: ['video_360_*', 'spatial_sound_*'],
        });
    }, [stream.streamReady, ctrl.mediaAdminKitRefreshToken]);

    const onRefreshKit = useCallback(() => {
        ctrl.bumpMediaAdminKitRefresh();
    }, [ctrl]);

    const onThemeChange = useCallback((theme: string) => {
        sendMessage('mediaContentThemeSet', { theme });
    }, []);

    const rowKey = (row: Video360RowModel | SpatialSoundRowModel) => `${row.kind}_${row.numericId}`;

    const getDraft = useCallback(
        (row: Video360RowModel | SpatialSoundRowModel) => {
            const k = rowKey(row);
            return draftByKey[k] || buildDraftFromRow(row);
        },
        [draftByKey],
    );

    const ensureDraft = useCallback((row: Video360RowModel | SpatialSoundRowModel) => {
        const k = rowKey(row);
        setDraftByKey((prev) => {
            if (prev[k]) return prev;
            return { ...prev, [k]: buildDraftFromRow(row) };
        });
    }, []);

    const setDraftField = useCallback((row: Video360RowModel | SpatialSoundRowModel, loc: LocaleCode, field: string, value: string) => {
        const k = rowKey(row);
        setDraftByKey((prev) => {
            const base = prev[k] || buildDraftFromRow(row);
            return {
                ...prev,
                [k]: {
                    ...base,
                    [loc]: { ...base[loc], [field]: value },
                },
            };
        });
    }, []);

    const exportPatchJson = useCallback(
        (row: Video360RowModel | SpatialSoundRowModel) => {
            const k = rowKey(row);
            const draft = draftByKey[k] || buildDraftFromRow(row);
            const base =
                row.kind === 'video360'
                    ? `icon_video_360_${row.numericId}`
                    : `icon_spatial_sound_${row.numericId}`;
            const fields = row.kind === 'video360' ? VIDEO360_I18N_FIELDS : SPATIAL_I18N_FIELDS;
            const out: Record<string, { interactions: Record<string, Record<string, string>> }> = {};
            for (const loc of LOCALES) {
                const block: Record<string, string> = {};
                for (const f of fields) {
                    block[f] = draft[loc][f] ?? '';
                }
                out[loc] = { interactions: { [base]: block } };
            }
            const blob = new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `media_admin_${base}_locales_bundle.json`;
            a.click();
            URL.revokeObjectURL(a.href);
        },
        [draftByKey],
    );

    const saveLocaleToKit = useCallback(
        (locale: LocaleCode, row: Video360RowModel | SpatialSoundRowModel) => {
            const k = rowKey(row);
            const draft = draftByKey[k] || buildDraftFromRow(row);
            const base =
                row.kind === 'video360'
                    ? `icon_video_360_${row.numericId}`
                    : `icon_spatial_sound_${row.numericId}`;
            const fields = row.kind === 'video360' ? VIDEO360_I18N_FIELDS : SPATIAL_I18N_FIELDS;
            const block: Record<string, string> = {};
            for (const f of fields) {
                block[f] = draft[locale][f] ?? '';
            }
            ctrl.setDevLocaleWriteStatus(null);
            sendMessage('devLocaleJsonWrite', {
                locale,
                patch: { interactions: { [base]: block } },
            });
        },
        [draftByKey, ctrl],
    );

    const rows = tab === 'video360' ? videoRows : spatialRows;

    return (
        <div style={panelStyle} role="dialog" aria-label={t('dev.mediaAdmin.title', 'Media content admin')}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h2 style={{ margin: 0, fontSize: 16 }}>{t('dev.mediaAdmin.title', 'Media content admin')}</h2>
                <button type="button" style={btnStyle} onClick={() => ctrl.setMediaAdminOpen(false)}>
                    {t('dev.mediaAdmin.close', 'Close')}
                </button>
            </div>

            <p style={{ margin: '0 0 10px', opacity: 0.85, lineHeight: 1.45 }}>
                {t(
                    'dev.mediaAdmin.blurb',
                    'Dev-only registry for 360° videos and spatial sounds: files on disk, USD Xforms from Kit, Kit-expanded interactions, and i18n gaps. Theme filters which iconGroup templates are active.',
                )}
            </p>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12, alignItems: 'center' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span>{t('dev.mediaAdmin.theme', 'Active media theme')}</span>
                    <select
                        value={ctrl.mediaContentTheme}
                        onChange={(e) => onThemeChange(e.target.value)}
                        style={{ padding: 6, borderRadius: 6, background: '#1a1d26', color: '#fff', border: '1px solid #444' }}
                    >
                        {THEMES.map((th) => (
                            <option key={th.id} value={th.id}>
                                {th.label}
                            </option>
                        ))}
                    </select>
                </label>
                <button type="button" style={btnStyle} onClick={onRefreshKit}>
                    {t('dev.mediaAdmin.refreshKit', 'Refresh Kit Xforms')}
                </button>
                <span style={{ fontSize: 11, opacity: 0.7 }}>
                    {t('dev.mediaAdmin.themeHint', 'Hockey pack: add a second iconGroup in interactions.json with contentThemes ["hockey"].')}
                </span>
            </div>

            {ctrl.devLocaleWriteStatus && (
                <div
                    style={{
                        marginBottom: 10,
                        padding: 8,
                        borderRadius: 8,
                        background: ctrl.devLocaleWriteStatus.ok ? 'rgba(40,120,60,0.25)' : 'rgba(120,40,40,0.3)',
                        border: '1px solid rgba(255,255,255,0.15)',
                    }}
                >
                    {ctrl.devLocaleWriteStatus.ok
                        ? t('dev.mediaAdmin.saveOk', 'Saved: {{msg}}', { msg: ctrl.devLocaleWriteStatus.message || '' })
                        : t('dev.mediaAdmin.saveErr', 'Save failed: {{msg}}', { msg: ctrl.devLocaleWriteStatus.error || 'unknown' })}
                </div>
            )}

            <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
                <button type="button" style={{ ...btnStyle, background: tab === 'video360' ? 'rgba(80,140,255,0.35)' : btnStyle.background }} onClick={() => setTab('video360')}>
                    360° video
                </button>
                <button type="button" style={{ ...btnStyle, background: tab === 'spatial' ? 'rgba(80,140,255,0.35)' : btnStyle.background }} onClick={() => setTab('spatial')}>
                    Spatial sound
                </button>
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                    <tr style={{ textAlign: 'left', borderBottom: '1px solid rgba(255,255,255,0.12)' }}>
                        <th style={{ padding: '6px 4px' }}>#</th>
                        <th style={{ padding: '6px 4px' }}>Media</th>
                        <th style={{ padding: '6px 4px' }}>Xform</th>
                        <th style={{ padding: '6px 4px' }}>Kit</th>
                        <th style={{ padding: '6px 4px' }}>Gaps</th>
                        <th style={{ padding: '6px 4px' }} />
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row) => {
                        const k = rowKey(row);
                        const isOpen = expandedRow?.kind === row.kind && expandedRow?.numericId === row.numericId;
                        const mediaName =
                            row.kind === 'video360'
                                ? (row as Video360RowModel).videoUrl || (row as Video360RowModel).mediaFiles[0] || '—'
                                : (row as SpatialSoundRowModel).soundUrl || (row as SpatialSoundRowModel).mediaFiles[0] || '—';
                        return (
                            <React.Fragment key={k}>
                                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                                    <td style={{ padding: '8px 4px', fontWeight: 700 }}>{row.numericId}</td>
                                    <td style={{ padding: '8px 4px', wordBreak: 'break-all' }}>{mediaName}</td>
                                    <td style={{ padding: '8px 4px' }}>
                                        {row.primNames.length ? row.primNames.join(', ') : '—'}
                                        {row.kitPositions[0]?.xyz && (
                                            <div style={{ opacity: 0.65, fontSize: 11 }}>
                                                ({row.kitPositions[0].xyz.map((n) => n.toFixed(1)).join(', ')})
                                            </div>
                                        )}
                                    </td>
                                    <td style={{ padding: '8px 4px' }}>{row.expandedInSession ? 'yes' : 'no'}</td>
                                    <td style={{ padding: '8px 4px', color: row.gaps.length ? '#fa9' : '#9c9' }}>
                                        {row.gaps.length ? row.gaps.join('; ') : 'ok'}
                                    </td>
                                    <td style={{ padding: '8px 4px' }}>
                                        <button
                                            type="button"
                                            style={{ ...btnStyle, padding: '4px 8px' }}
                                            onClick={() => {
                                                if (isOpen) {
                                                    setExpandedRow(null);
                                                } else {
                                                    ensureDraft(row);
                                                    setExpandedRow(row);
                                                }
                                            }}
                                        >
                                            {isOpen ? '▲' : '▼'} i18n
                                        </button>
                                    </td>
                                </tr>
                                {isOpen && (
                                    <tr>
                                        <td colSpan={6} style={{ padding: '10px 4px 16px', background: 'rgba(0,0,0,0.2)' }}>
                                            {LOCALES.map((loc) => (
                                                <div key={loc} style={{ marginBottom: 14 }}>
                                                    <div style={{ fontWeight: 700, marginBottom: 6 }}>{loc.toUpperCase()}</div>
                                                    {(row.kind === 'video360' ? VIDEO360_I18N_FIELDS : SPATIAL_I18N_FIELDS).map((field) => (
                                                        <label key={field} style={{ display: 'block', marginBottom: 6 }}>
                                                            <span style={{ display: 'inline-block', width: 88, opacity: 0.75 }}>{field}</span>
                                                            <input
                                                                style={{
                                                                    width: 'calc(100% - 96px)',
                                                                    padding: 6,
                                                                    borderRadius: 4,
                                                                    border: '1px solid #444',
                                                                    background: '#11141c',
                                                                    color: '#fff',
                                                                }}
                                                                value={getDraft(row)[loc][field] ?? ''}
                                                                onChange={(e) => setDraftField(row, loc, field, e.target.value)}
                                                            />
                                                        </label>
                                                    ))}
                                                    <button type="button" style={{ ...btnStyle, marginTop: 6 }} onClick={() => saveLocaleToKit(loc, row)}>
                                                        {t('dev.mediaAdmin.saveKit', 'Save {{loc}} via Kit', { loc })}
                                                    </button>
                                                </div>
                                            ))}
                                            <button type="button" style={{ ...btnStyle, marginTop: 8 }} onClick={() => exportPatchJson(row)}>
                                                {t('dev.mediaAdmin.exportJson', 'Export all locales JSON (merge manually)')}
                                            </button>
                                        </td>
                                    </tr>
                                )}
                            </React.Fragment>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
};

export default MediaAdminPanel;
