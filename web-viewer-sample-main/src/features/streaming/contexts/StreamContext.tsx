import React, { createContext, useContext } from 'react';
import { useStreamConnection } from '../hooks/useStreamConnection';

export type StreamContextType = ReturnType<typeof useStreamConnection>;

const StreamContext = createContext<StreamContextType | null>(null);

export function StreamProvider({ userId, onStreamFailed, isViewer, children }: {
    userId: string | undefined;
    onStreamFailed?: () => void;
    isViewer?: boolean;
    children: React.ReactNode;
}) {
    const value = useStreamConnection(userId, onStreamFailed, isViewer);
    return <StreamContext.Provider value={value}>{children}</StreamContext.Provider>;
}

export function useStream(): StreamContextType {
    const ctx = useContext(StreamContext);
    if (!ctx) throw new Error('useStream must be used within StreamProvider');
    return ctx;
}

export { StreamContext };
