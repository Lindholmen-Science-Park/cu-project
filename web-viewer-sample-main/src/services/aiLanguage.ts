/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 *
 * Centralised mapping from the UI language (i18next) to the language we send
 * to the Kit-side AI agent.
 *
 * The AI chat backend currently only supports English (`en`) and Swedish (`sv`).
 * Any other UI locale (e.g. `fr`, `es`) is mapped to `en` so the agent can
 * still respond. This is by design until the agent gains additional language
 * support.
 */

const AI_SUPPORTED_LANGS = new Set(['en', 'sv']);

/**
 * Map a UI locale (i18next `language`, possibly with a region tag like `en-US`)
 * to the language code accepted by the AI agent. Falls back to `en` for
 * unsupported locales or empty input.
 */
export function aiLanguageFor(uiLang: string | undefined | null): string {
    if (!uiLang) return 'en';
    const base = String(uiLang).split('-')[0].toLowerCase();
    return AI_SUPPORTED_LANGS.has(base) ? base : 'en';
}
