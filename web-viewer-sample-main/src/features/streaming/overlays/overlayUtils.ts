export type ContentRect = { left: number; top: number; width: number; height: number };

/**
 * Compute the actual content rectangle of a video element using object-fit: cover math.
 * The video fills the element and overflows on one axis; the returned rect extends
 * beyond the element bounds so Kit viewport pixel coords map correctly.
 */
export function computeVideoContentRect(video: HTMLVideoElement): ContentRect | null {
    const rect = video.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return null;

    const videoW = video.videoWidth || 1920;
    const videoH = video.videoHeight || 1080;
    const elementAspect = rect.width / rect.height;
    const videoAspect = videoW / videoH;

    let contentLeft = rect.left;
    let contentTop = rect.top;
    let contentWidth = rect.width;
    let contentHeight = rect.height;

    if (elementAspect > videoAspect) {
        contentHeight = rect.width / videoAspect;
        contentTop = rect.top - (contentHeight - rect.height) / 2;
    } else if (elementAspect < videoAspect) {
        contentWidth = rect.height * videoAspect;
        contentLeft = rect.left - (contentWidth - rect.width) / 2;
    }

    return { left: contentLeft, top: contentTop, width: contentWidth, height: contentHeight };
}
