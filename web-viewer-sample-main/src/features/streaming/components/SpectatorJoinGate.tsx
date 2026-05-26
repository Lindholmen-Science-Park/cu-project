import React from 'react';
import { useTranslation } from 'react-i18next';
import './SpectatorJoinGate.css';

export interface SpectatorJoinGateProps {
    onJoin: () => void;
}

const SpectatorJoinGate: React.FC<SpectatorJoinGateProps> = ({ onJoin }) => {
    const { t } = useTranslation();
    return (
        <div className="spectator-join-gate">
            <div className="spectator-join-gate__badge">{t('streaming.spectatorMode')}</div>
            <div className="spectator-join-gate__title">{t('streaming.readyToJoin')}</div>
            <button type="button" className="spectator-join-gate__cta" onClick={onJoin}>
                {t('streaming.joinSession')}
            </button>
            <div className="spectator-join-gate__hint">{t('streaming.viewOnlyDescription')}</div>
        </div>
    );
};

export default SpectatorJoinGate;
