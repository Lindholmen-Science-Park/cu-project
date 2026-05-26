/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 */

export const CONNECT_TIMEOUT_MS = 15000;
export const MAX_CONNECT_RETRIES = 3;
export const ORIENTATION_DEBOUNCE_MS = 500;
export const RESIZE_RECONNECT_COOLDOWN_MS = 8000;

export function getEffectiveServer(configServer: string): string {
    if (typeof window === 'undefined') return configServer;
    const h = window.location.hostname;
    if (h === 'localhost' || h === '127.0.0.1') return configServer;
    return h;
}

// Compute an encoder-safe resolution that preserves the viewport's aspect ratio.
// Width is 32-aligned, height is 16-aligned — satisfies NVENC macroblock constraints.
export function getAlignedResolution(vpWidth: number, vpHeight: number): { width: number; height: number } {
    const MIN_W = 640;
    const MAX_W = 1920;
    const MAX_H = 1440;
    const ar = vpHeight / vpWidth;

    const scale = Math.min(MAX_W / vpWidth, MAX_H / vpHeight, 1.0);
    let w = Math.max(Math.floor((vpWidth * scale) / 32) * 32, MIN_W);
    let h = Math.round((w * ar) / 16) * 16;
    return { width: w, height: h };
}
