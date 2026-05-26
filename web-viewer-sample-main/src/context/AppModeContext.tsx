import React, { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

export type AppMode = 'dev' | 'cu';

interface AppModeContextValue {
    mode: AppMode;
    setMode: (mode: AppMode) => void;
}

const AppModeContext = createContext<AppModeContextValue>({
    mode: 'cu',
    setMode: () => {},
});

export const AppModeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [mode, setModeState] = useState<AppMode>('cu');

    const setMode = useCallback((next: AppMode) => {
        setModeState(next);
    }, []);

    return (
        <AppModeContext.Provider value={{ mode, setMode }}>
            {children}
        </AppModeContext.Provider>
    );
};

export const useAppMode = () => {
    const { mode, setMode } = useContext(AppModeContext);
    return { mode, setMode };
};
