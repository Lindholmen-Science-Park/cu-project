import React, { createContext, useContext } from 'react';
import { useEnvironmentHandlers } from '../hooks/useEnvironmentHandlers';
import { useStream } from './StreamContext';

export type EnvironmentContextType = ReturnType<typeof useEnvironmentHandlers>;

const EnvironmentContext = createContext<EnvironmentContextType | null>(null);

export function EnvironmentProvider({ children }: { children: React.ReactNode }) {
    const { streamReady } = useStream();
    const value = useEnvironmentHandlers(streamReady);
    return <EnvironmentContext.Provider value={value}>{children}</EnvironmentContext.Provider>;
}

export function useEnvironment(): EnvironmentContextType {
    const ctx = useContext(EnvironmentContext);
    if (!ctx) throw new Error('useEnvironment must be used within EnvironmentProvider');
    return ctx;
}

export { EnvironmentContext };
