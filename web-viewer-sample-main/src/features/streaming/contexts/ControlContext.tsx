import React, { createContext, useContext } from 'react';
import { useControlHandlers } from '../hooks/useControlHandlers';

export type ControlContextType = ReturnType<typeof useControlHandlers>;

const ControlContext = createContext<ControlContextType | null>(null);

export function ControlProvider({ children }: { children: React.ReactNode }) {
    const value = useControlHandlers();
    return <ControlContext.Provider value={value}>{children}</ControlContext.Provider>;
}

export function useControl(): ControlContextType {
    const ctx = useContext(ControlContext);
    if (!ctx) throw new Error('useControl must be used within ControlProvider');
    return ctx;
}

export { ControlContext };
