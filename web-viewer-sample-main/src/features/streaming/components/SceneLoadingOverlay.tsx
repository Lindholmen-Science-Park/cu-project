import React from 'react';
import { useTranslation } from 'react-i18next';
import { useStream } from '../contexts';
import { LoadingScreen } from './loading';

/**
 * Full-purple blocker shown while Kit reports `scene.loading` (between WebRTC
 * connect and `scene.loaded`). Surfaces a "Re-request status" CTA when the
 * load is taking longer than expected.
 */
const SceneLoadingOverlay: React.FC = () => {
    const stream = useStream();
    const { t } = useTranslation();

    if (!stream.sceneLoading) return null;

    const message = stream.loadingPhase.message || t('loading.loadingScene');
    const phase = stream.loadingPhase.phase;
    const showRerequest =
        message.includes('longer than expected') || phase === 'waiting';

    return (
        <LoadingScreen
            message={message}
            actionLabel={showRerequest ? t('loading.reRequestStatus') : undefined}
            onAction={showRerequest ? stream.handleRerequestSceneStatus : undefined}
        />
    );
};

export default SceneLoadingOverlay;
