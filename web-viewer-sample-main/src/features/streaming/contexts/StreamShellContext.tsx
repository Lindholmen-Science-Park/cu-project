import React, { createContext, useContext, useState, useMemo, type ReactNode } from 'react';

export interface StreamShellContextType {
    /** Spectator has tapped “Join session” (persists for this mount only). */
    viewerJoined: boolean;
    setViewerJoined: React.Dispatch<React.SetStateAction<boolean>>;
    isViewer: boolean;
}

const StreamShellContext = createContext<StreamShellContextType | null>(null);

export function StreamShellProvider({
    isViewer,
    children,
}: {
    isViewer: boolean;
    children: ReactNode;
}) {
    const [viewerJoined, setViewerJoined] = useState(false);
    const value = useMemo(
        () => ({ viewerJoined, setViewerJoined, isViewer }),
        [viewerJoined, isViewer],
    );
    return <StreamShellContext.Provider value={value}>{children}</StreamShellContext.Provider>;
}

export function useStreamShell(): StreamShellContextType {
    const ctx = useContext(StreamShellContext);
    if (!ctx) {
        throw new Error('useStreamShell must be used within StreamShellProvider');
    }
    return ctx;
}
