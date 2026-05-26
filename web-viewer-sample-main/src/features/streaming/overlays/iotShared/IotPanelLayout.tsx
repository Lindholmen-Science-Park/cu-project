import React from 'react';
import { useIotPanelDrag } from './useIotPanelDrag';

export type IotPanelLayoutProps = {
    open: boolean;
    onDismiss: () => void;
    titleId: string;
    /** Drag-handle label (dev UI; English default). */
    dragLabel?: string;
    children: React.ReactNode;
};

/**
 * Streaming IoT list panels: desktop keeps corner card; narrow viewports use a bottom sheet
 * with drag-to-dismiss, capped height, and safe-area padding.
 */
const IotPanelLayout: React.FC<IotPanelLayoutProps> = ({
    open,
    onDismiss,
    titleId,
    dragLabel = 'Drag down to close',
    children,
}) => {
    const drag = useIotPanelDrag(open, onDismiss);

    return (
        <div className="iot-air-stations-backdrop" role="presentation">
            <div
                className={`iot-air-stations-sheet-outer${drag.isMobile ? ' iot-air-stations-sheet-outer--mobile' : ''}`}
                style={drag.sheetOuterStyle}
            >
                <button
                    type="button"
                    className="iot-air-stations-drag-handle"
                    tabIndex={drag.isMobile ? 0 : -1}
                    aria-hidden={!drag.isMobile}
                    aria-label={drag.isMobile ? dragLabel : undefined}
                    onPointerDown={drag.onHandlePointerDown}
                    onPointerMove={drag.onHandlePointerMove}
                    onPointerUp={drag.onHandlePointerUp}
                    onPointerCancel={drag.onHandlePointerCancel}
                >
                    <span className="iot-air-stations-drag-handle-pill" aria-hidden />
                </button>
                <aside
                    className="iot-air-stations-panel"
                    role="dialog"
                    aria-modal="false"
                    aria-labelledby={titleId}
                >
                    {children}
                </aside>
            </div>
        </div>
    );
};

export default IotPanelLayout;
