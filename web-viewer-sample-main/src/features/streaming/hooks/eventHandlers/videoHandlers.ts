import type { VideoConfig } from '../../overlays/videoPlayer/VideoPlayerOverlay';
import type { EventStateSetters } from './types';

export function handleVideoEvents(event: any, s: EventStateSetters): void {
    if (event.event_type === 'videoListSync') {
        try {
            const p = event.payload || {};
            const videos: VideoConfig[] = Array.isArray(p.videos) ? p.videos : [];
            s.setVideoList(videos);
            console.log(`[video] Synced ${videos.length} video(s) from Kit`);
        } catch {}
        return;
    }

    if (event.event_type === 'videoOpen') {
        try {
            const p = event.payload || {};
            const video: VideoConfig = {
                id: String(p.id || ''),
                title: String(p.title || 'Video'),
                description: p.description ? String(p.description) : undefined,
                source: String(p.source || ''),
                durationSeconds: p.durationSeconds ? Number(p.durationSeconds) : undefined,
                onCompleteAction: p.onCompleteAction || undefined,
            };
            if (video.source) {
                s.setVideoPlayerConfig(video);
                s.setVideoPlayerOpen(true);
            }
        } catch {}
        return;
    }
}
