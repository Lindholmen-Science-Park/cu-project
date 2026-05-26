import React from 'react';
import type { RouteErrorAnnouncement } from '../utils/navRouteErrorMessages';

export interface RouteErrorAlertProps {
    error: RouteErrorAnnouncement;
    id?: string;
}

/**
 * WCAG 4.1.3 — assertive live region for Kit route failures on POI / directions flows.
 * Screen-reader only until design supplies visible error copy (see `wcag-accessibility.mdc`).
 */
const RouteErrorAlert: React.FC<RouteErrorAlertProps> = ({ error, id }) => (
    <div id={id} className="sr-only" role="alert" aria-live="assertive">
        {error.suggestion ? `${error.title} ${error.suggestion}` : error.title}
    </div>
);

export default RouteErrorAlert;
