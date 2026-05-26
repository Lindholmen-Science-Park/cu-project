import React from 'react';
import { useTranslation } from 'react-i18next';
import './WelcomeAvatarOverlay.css';
import interactivePointerSvg from '@icons/interaction/interactive-pointer.svg';

const avatarModules: Record<string, string> = {};
const rawModules = import.meta.glob(
    '@kit-avatars/*.{png,jpg,webp}',
    { eager: true, import: 'default' },
);
for (const [path, url] of Object.entries(rawModules)) {
    const filename = path.split('/').pop();
    if (filename) avatarModules[filename] = url as string;
}

interface WelcomeAvatarOverlayProps {
    avatarImage?: string;
    /** Klikkaus avatarista → esim. Avatar Chat */
    onAvatarPress?: () => void;
}

/**
 * Bird's eye -näkymän welcome-avatar ilman puhekuplaa (tervehdys vain chatissa).
 */
const WelcomeAvatarOverlay: React.FC<WelcomeAvatarOverlayProps> = ({
    avatarImage = 'red_wave.png',
    onAvatarPress,
}) => {
    const { t } = useTranslation();
    const imgUrl = avatarModules[avatarImage];

    const handleAvatarPress = (e: React.MouseEvent) => {
        e.stopPropagation();
        onAvatarPress?.();
    };

    return (
        <div className="welcome-avatar-root">
            <div className="welcome-avatar-wrapper">
                {imgUrl &&
                    (onAvatarPress ? (
                        <button
                            type="button"
                            className="welcome-avatar-image-btn"
                            title={t('avatar.openChat')}
                            aria-label={t('avatar.openChatWithGuide')}
                            onClick={handleAvatarPress}
                        >
                            <img
                                className="welcome-avatar-interactive-pointer"
                                src={interactivePointerSvg}
                                alt=""
                                aria-hidden="true"
                                draggable={false}
                            />
                            <img
                                className="welcome-avatar-image"
                                src={imgUrl}
                                alt={t('avatar.welcomeAvatar')}
                                draggable={false}
                            />
                        </button>
                    ) : (
                        <img
                            className="welcome-avatar-image"
                            src={imgUrl}
                            alt={t('avatar.welcomeAvatar')}
                        />
                    ))}
            </div>
        </div>
    );
};

export default WelcomeAvatarOverlay;
