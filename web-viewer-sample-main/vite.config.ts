/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */
import { defineConfig } from "vite";
import { resolve } from "path";
import { viteExternalsPlugin } from 'vite-plugin-externals';
import cesium from 'vite-plugin-cesium';
import react from "@vitejs/plugin-react";
// https://vitejs.dev/config/
export default defineConfig({
    plugins: [
        react(),
        cesium(),
        viteExternalsPlugin({
            GFN: 'GFN'
        }),
    ],
    envDir: resolve(__dirname, '..'),
    envPrefix: ['VITE_', 'CESIUM_'],
    resolve: {
        alias: {
            '@icons': resolve(__dirname, 'src/icons'),
            '@kit-avatars': resolve(__dirname, '../kit-app-template-main/source/data/Assets/Avatars'),
            '@kit-videos': resolve(__dirname, '../kit-app-template-main/source/data/Assets/Videos'),
            '@nucleus-videos': resolve(__dirname, '../kit-app-template-main/source/data/nucleus/videos'),
            // Audio root — globbed RECURSIVELY by SpatialSoundOverlay,
            // ambientSoundEngine and mediaRegistryUtils via `@nucleus-sounds/**`.
            // Filenames are looked up by basename, so subfolder layout
            // (spatial/, ambient/, ui/, …) is purely organisational and must
            // stay unique across subfolders. Mirror the Kit indexer with
            // `iconConfig.soundsDir` in `kit-app-template-main/source/data/interactions.json`.
            '@nucleus-sounds': resolve(__dirname, '../kit-app-template-main/source/data/nucleus/sounds'),
        },
    },
    server: {
        host: true,
        fs: {
            allow: ['.', '../kit-app-template-main/source/data'],
        },
    },
});
