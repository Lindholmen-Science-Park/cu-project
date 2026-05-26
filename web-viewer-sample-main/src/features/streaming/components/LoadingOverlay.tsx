import React from 'react';
import { useTranslation } from 'react-i18next';
import { useStream } from '../contexts';
import { LoadingScreen } from './loading';

/**
 * Initial WebRTC boot blocker. Stays visible until `streamReady` flips.
 * On timeout/failure surfaces a Retry CTA inside the brand loading screen.
 */
const LoadingOverlay: React.FC = () => {
    const stream = useStream();
    const { t } = useTranslation();

    if (stream.streamReady) return null;

    const showRetry = stream.loadingText.includes('timeout') || stream.loadingText.includes('failed');

    return (
        <LoadingScreen
            message={stream.loadingText}
            actionLabel={showRetry ? t('loading.retryConnection') : undefined}
            onAction={showRetry ? () => stream.retryConnection() : undefined}
        />
    );
};

export default LoadingOverlay;
