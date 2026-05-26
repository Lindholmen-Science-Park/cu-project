import React, { createContext, useContext } from 'react';
import { useNavigationHandlers } from '../hooks/navigationHandlers';
import { useStream } from './StreamContext';
import { useEnvironment } from './EnvironmentContext';

export type NavigationContextType = ReturnType<typeof useNavigationHandlers>;

const NavigationContext = createContext<NavigationContextType | null>(null);

export function NavigationProvider({ children }: { children: React.ReactNode }) {
    const { streamReady } = useStream();
    const { currentCamera, setCurrentCamera } = useEnvironment();
    const value = useNavigationHandlers(streamReady, currentCamera, setCurrentCamera);
    return <NavigationContext.Provider value={value}>{children}</NavigationContext.Provider>;
}

export function useNavigation(): NavigationContextType {
    const ctx = useContext(NavigationContext);
    if (!ctx) throw new Error('useNavigation must be used within NavigationProvider');
    return ctx;
}

export { NavigationContext };
