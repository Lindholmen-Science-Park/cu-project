import React from 'react';
import { useTranslation } from 'react-i18next';
import citiversesLogo from '@icons/loading/citiverses-logo.svg';
import euCofunded from '@icons/loading/eu-cofunded.png';
import './LoadingFooter.css';

/**
 * Shared bottom-of-viewport credit block: Citiverses logo + EU co-funding lockup +
 * the legally required EU disclaimer copy. Used by both the full-purple and
 * see-through loading screens.
 */
const LoadingFooter: React.FC = () => {
    const { t } = useTranslation();

    return (
        <footer className="loading-footer">
            <div className="loading-footer__logos">
                <img
                    src={citiversesLogo}
                    alt="European Citiverses — Uniting for Inclusiveness"
                    className="loading-footer__logo loading-footer__logo--citiverses"
                />
                <img
                    src={euCofunded}
                    alt={t('loading.euCofunded')}
                    className="loading-footer__logo loading-footer__logo--eu"
                />
            </div>
            <p className="loading-footer__disclaimer">
                {t('loading.euDisclaimer')}
            </p>
        </footer>
    );
};

export default LoadingFooter;
