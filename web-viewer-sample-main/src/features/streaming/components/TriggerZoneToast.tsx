import React from 'react';
import { useTranslation } from 'react-i18next';
import { useControl } from '../contexts';

const TriggerZoneToast: React.FC = () => {
    const { t } = useTranslation();
    const ctrl = useControl();
    const n = ctrl.triggerZoneNotification;
    if (!n) return null;

    const { message, zoneType } = n;
    const onDismiss = () => ctrl.setTriggerZoneNotification(null);

    return (
    <>
        <div
            className="trigger-zone-toast"
            role="status"
            aria-live="polite"
            aria-atomic="true"
        >
            <span className="trigger-zone-toast__icon" aria-hidden>
                {zoneType === 'navigation_arrival' ? '\u2714' : '\u26A0'}
            </span>
            <span>{message}</span>
            <button
                type="button"
                className="trigger-zone-toast__close"
                onClick={onDismiss}
                aria-label={t('common.close')}
            >
                {'\u2715'}
            </button>
        </div>
        <style>{`
            .trigger-zone-toast {
                position: absolute;
                bottom: 40px;
                left: 50%;
                transform: translateX(-50%);
                background-color: rgba(0, 0, 0, 0.85);
                color: #fff;
                padding: 14px 28px;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 500;
                display: flex;
                align-items: center;
                gap: 10px;
                z-index: 2000;
                backdrop-filter: blur(8px);
                border: 1px solid rgba(118, 185, 0, 0.4);
                box-shadow: 0 4px 24px rgba(0,0,0,0.5);
                animation: triggerZoneToastIn 0.3s ease-out;
                pointer-events: auto;
                max-width: 90vw;
            }
            .trigger-zone-toast__close {
                background: none;
                border: none;
                color: rgba(255,255,255,0.6);
                font-size: 18px;
                cursor: pointer;
                padding: 0 0 0 8px;
                line-height: 1;
                min-width: 44px;
                min-height: 44px;
            }
            @keyframes triggerZoneToastIn {
                from { opacity: 0; transform: translateX(-50%) translateY(20px); }
                to   { opacity: 1; transform: translateX(-50%) translateY(0); }
            }
        `}</style>
    </>
    );
};

export default TriggerZoneToast;
