/**
 * Figma design file reference – 2026 APRIL DEMO_Designs
 * Use these URLs to open the correct frame in Figma (Dev mode).
 */
export const FIGMA_FILE_KEY = 'vnlxvc8YpXncYM1HfEulQk';
export const FIGMA_BASE_URL = `https://www.figma.com/design/${FIGMA_FILE_KEY}/2026-APRIL-DEMO_Designs`;

/** Node IDs for quick linking (append ?node-id=XXXX-XXXX&m=dev) */
export const FIGMA_NODES = {
    /** CU mode menu button */
    menuButton: '5721-7121',
    /** People / Groups panel */
    peoplePanel: '5721-7131',
    /** People content card */
    peopleCard: '1505-6613',
    /** General frame (e.g. layout) */
    frame: '1505-6675',
} as const;

/** Build Figma URL for a node (opens in Dev mode) */
export function getFigmaNodeUrl(nodeId: string): string {
    return `${FIGMA_BASE_URL}?node-id=${nodeId}&m=dev`;
}

export const figmaUrls = {
    menuButton: getFigmaNodeUrl(FIGMA_NODES.menuButton),
    peoplePanel: getFigmaNodeUrl(FIGMA_NODES.peoplePanel),
    peopleCard: getFigmaNodeUrl(FIGMA_NODES.peopleCard),
    frame: getFigmaNodeUrl(FIGMA_NODES.frame),
} as const;
