/**
 * Ambient type declarations for the Google Chrome `omnitone` package.
 *
 * `omnitone@1.3.x` ships as a single UMD/IIFE script (`build/omnitone.js`) with
 * **no ESM or CJS exports** — it just assigns to a global `Omnitone`.  Vite's
 * dev server (esbuild) is permissive about that, but the production Rollup
 * build rejects `import Omnitone from 'omnitone'`.  We therefore load it via
 * `?url` import + dynamic <script> injection (see useAmbisonicPlayer.ts) and
 * read `window.Omnitone` once it has loaded.
 */

export interface FOARenderer {
    input: AudioNode;
    output: AudioNode;
    initialize: () => Promise<void>;
    setRotationMatrix3: (matrix: Float32Array) => void;
    setRotationMatrix4: (matrix: Float32Array) => void;
    setChannelMap: (channelMap: number[]) => void;
    setRenderingMode: (mode: 'ambisonic' | 'bypass' | 'off') => void;
}

export interface FOARendererConfig {
    ambisonicOrder?: number;
    channelMap?: number[];
    hrirPathList?: string[];
    renderingMode?: 'ambisonic' | 'bypass' | 'off';
}

export interface OmnitoneApi {
    createFOARenderer(context: BaseAudioContext, config?: FOARendererConfig): FOARenderer;
    createHOARenderer(context: BaseAudioContext, config?: Record<string, unknown>): FOARenderer;
}

declare global {
    interface Window {
        Omnitone?: OmnitoneApi;
    }
}

declare module 'omnitone/build/omnitone.js?url' {
    const url: string;
    export default url;
}
