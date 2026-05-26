/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

/*
 * The Web Viewer Sample is configured by default to connect to the USD Viewer application template and includes web UI
 * elements for sending messages to a running Kit application. This is necessary for the USD Viewer template, which in
 * the default use case requires a client to send a request to open a file.
 */
import 'bootstrap/dist/css/bootstrap.min.css';
import { AppStreamer } from '@nvidia/omniverse-webrtc-streaming-library';
import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { safeTerminateStream } from '../features/streaming/streamUtils';
import "./App.css";
import StreamOnlyWindow from '../features/streaming/StreamOnlyWindow';
import { Application, ServerURLsForm, ApplicationsForm, VersionsForm, ProfilesForm } from "../features/streaming/connection/Forms"
import StreamConfig from '../config/stream.config.json';
import { AppModeProvider } from '../context/AppModeContext';
import {
    getStreamingSessionInfo,
    createStreamingSession,
    destroyStreamingSession,
    StreamItem
} from '../features/streaming/connection/Endpoints';

// Debug flag to control console filtering
const ENABLE_CONSOLE_FILTERING = true; // Set to false to see all messages

// Filter out verbose streaming library messages from console
const originalConsoleLog = console.log;
if (ENABLE_CONSOLE_FILTERING) {
    console.log = (...args: any[]) => {
        // Check if any argument contains verbose streaming library patterns
        const shouldFilter = args.some(arg => {
            if (typeof arg === 'string') {
                return arg.includes('"type":"info","title":"unknown","status":100') ||
                       arg.includes('"type":"info","title":"success","status":200') ||
                       (arg.includes('"detail":"{') && arg.includes('}##[')) ||
                       arg.includes('"detail":"{') && arg.includes('}","request":"message"');
            }
            if (typeof arg === 'object' && arg !== null) {
                const o = arg as Record<string, any>;
                if (o.type === 'info' && o.title === 'success' && o.status === 200) return true;
                const str = JSON.stringify(arg);
                return str.includes('"type":"info","title":"unknown","status":100') ||
                       str.includes('"type":"info","title":"success","status":200') ||
                       (str.includes('"detail":"{') && str.includes('}##[')) ||
                       (str.includes('"detail":"{') && str.includes('}","request":"message"'));
            }
            return false;
        });
        
        // Only log if it doesn't match the verbose patterns
        if (!shouldFilter) {
            originalConsoleLog.apply(console, args);
        }
    };
}


enum StreamStatus {
    IDLE,
    INITIALIZING,
    INITIALIZED
}

export enum Forms {
    IDLE,
    AppOnly,
    StreamURLs,
    Applications,
    Versions,
    Profiles,
    Stream,
    StreamOnly
}


const App: React.FC = () => {
    const { t } = useTranslation();
    const [currentForm, setCurrentForm] = useState<Forms>(
        StreamConfig.source === "local" ? Forms.Stream : Forms.StreamURLs
    );
    const [streamServer, setStreamServer] = useState(StreamConfig.stream.streamServer);
    const [appServer, setAppServer] = useState(StreamConfig.stream.appServer);
    const [applications, setApplications] = useState<Application[]>([]);
    const [applicationVersions, setApplicationVersions] = useState<string[]>([]);
    const [applicationProfiles, setApplicationProfiles] = useState<string[]>([]);
    const [selectedApplicationId, setSelectedApplicationId] = useState('');
    const [selectedApplicationVersion, setSelectedApplicationVersion] = useState('');
    const [, setSelectedApplicationProfile] = useState('');
    const [streamStatus, setStreamStatus] = useState<StreamStatus>(StreamStatus.IDLE);
    const [connectionText, setConnectionText] = useState('');
    const [backendUrl, setBackendUrl] = useState('');
    const [signalingserver, setSignalingserver] = useState(
        StreamConfig.source === "local" ? StreamConfig.local.server : ''
    );
    const [signalingport, setSignalingport] = useState(
        StreamConfig.source === "local" ? StreamConfig.local.signalingPort : 0
    );
    const [mediaserver, setMediaserver] = useState(
        StreamConfig.source === "local" ? StreamConfig.local.server : ''
    );
    const [mediaport, setMediaport] = useState(
        StreamConfig.source === "local" ? (StreamConfig.local.mediaPort || 0) : 0
    );
    const [accessToken, setAccessToken] = useState('');
    const [sessionId, setSessionId] = useState('');
    const [userId, setUserId] = useState(`user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
    const [isViewer] = useState(() => new URLSearchParams(window.location.search).get('viewer') === 'true');

    /**
     * Ends the currently running stream by the unique ID
     */
    const endStream = useCallback(async () => {
        if (!sessionId) {
            return;
        }

        try {
            const response = await getStreamingSessionInfo(streamServer, sessionId);
            if (response.status !== 200) {
                return;
            }
            
            const destroyResponse = await destroyStreamingSession(streamServer, sessionId);
            if ('detail' in destroyResponse) {
                console.warn(`Failed to destroy session: ${destroyResponse.detail}`);
                return;
            }

            console.info(`Streaming Session ${sessionId} Destroyed`);
        } catch (error) {
            console.warn(`Error destroying session ${sessionId}:`, error);
        }
    }, [sessionId, streamServer]);

    useEffect(() => {
        // For local configuration, automatically start the stream
        if (StreamConfig.source === "local") {
            setStreamStatus(StreamStatus.INITIALIZED);
            setCurrentForm(Forms.Stream);
        }
        
        // Cleanup on unmount
        return () => {
            if (sessionId) {
                endStream().catch(error => {
                    console.warn('Failed to cleanup session on unmount:', error);
                });
            }
            safeTerminateStream();
        };
    }, [sessionId, endStream]);

    /**
     * Clean up only this user's session (multi-user friendly)
     */
    const cleanupUserSession = useCallback(async () => {
        if (StreamConfig.source === "stream" && streamServer && sessionId) {
            try {
                // Only destroy this user's specific session
                await destroyStreamingSession(streamServer, sessionId);
                console.info(`User ${userId} session ${sessionId} cleaned up`);
            } catch (error) {
                console.warn(`Failed to cleanup user ${userId} session ${sessionId}:`, error);
            }
        }
    }, [streamServer, sessionId, userId]);

    // Clean up user session on mount (multi-user friendly)
    useEffect(() => {
        // Only cleanup this user's session, not all sessions
        if (sessionId) {
            cleanupUserSession();
        }
    }, [sessionId, cleanupUserSession]);

    /**
     * Resets application state to default values
     */
    const resetState = useCallback(() => {
        setCurrentForm(StreamConfig.source === "local" ? Forms.Stream : Forms.StreamURLs);
        setStreamServer(StreamConfig.stream.streamServer);
        setAppServer(StreamConfig.stream.appServer);
        setApplications([]);
        setApplicationVersions([]);
        setApplicationProfiles([]);
        setSelectedApplicationId('');
        setSelectedApplicationVersion('');
        setSelectedApplicationProfile('');
        setStreamStatus(StreamStatus.IDLE);
        setConnectionText('');
        setBackendUrl('');
        setSignalingserver(StreamConfig.source === "local" ? StreamConfig.local.server : '');
        setSignalingport(StreamConfig.source === "local" ? StreamConfig.local.signalingPort : 0);
        setMediaserver(StreamConfig.source === "local" ? StreamConfig.local.server : '');
        setMediaport(StreamConfig.source === "local" ? (StreamConfig.local.mediaPort || 0) : 0);
        setAccessToken('');
        setSessionId('');
        setUserId(`user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
    }, []);

    /**
     * Polls for the session to be ready
     * 
     * @param sessionId - The ID of the session
     */
    const pollForSessionReady = useCallback(async (sessionId: string) => {
        try {
            console.info("polling for session");
            const response = await getStreamingSessionInfo(streamServer, sessionId);
            if (response.status === 200) {
                console.info("Session is ready. Waiting before setup...");
                //await this.sleep(30000); // 5 seconds delay, hardcoded for testing
                console.info("Delay complete. Setting up stream...");
                setupStream(response.data as StreamItem);
            }
            else {
                setTimeout(() => pollForSessionReady(sessionId), 10000);
                console.log( `Waiting for session ${sessionId} to be ready... Last checked at ${new Date().toLocaleTimeString()}`)
            }
        } catch (error) {
            console.error('Error polling session info:', error);
        }
    }, [streamServer]);

    /**
     * Sets up the stream with the created stream data
     * 
     * @param createdStream - The created stream data
     */
    const setupStream = useCallback((createdStream: StreamItem) => {
        console.info("createdStream", createdStream);
        
        const sessionId = createdStream.id;
        const serverIP = Object.keys(createdStream.routes)[0];
        const routeData = createdStream.routes[serverIP].routes;

        const signalingData = routeData.find((item: any) => item.description === 'signaling');
        const mediaData = routeData.find((item: any) => item.description === 'media');
    
        if (!signalingData || !mediaData) {
            console.error('Signaling or media data is missing');
            return;
        }
                    
        setBackendUrl(`${streamServer}/streaming/stream`);
        setSignalingserver(serverIP);
        setSignalingport(signalingData.source_port);
        setMediaserver(serverIP);
        setMediaport(mediaData.source_port);
        setAccessToken('');
        setSessionId(sessionId);
        setCurrentForm(Forms.Stream);
        setStreamStatus(StreamStatus.INITIALIZED);
    }, [streamServer]);

    /**
     * Creates and sets up a new streaming session
     * 
     * @param appId - The ID of the Kit application
     * @param version - The version of the Kit application
     * @param profile - The profile of the Kit application
     * @returns 
     */
    const startStream = useCallback(async (appId: string, version: string, profile: string) => {
        // Clean up only this user's existing session (multi-user friendly)
        if (sessionId) {
            try {
                await endStream();
            } catch (error) {
                console.warn(`Failed to cleanup user ${userId} existing session:`, error);
            }
        }
        
        setCurrentForm(Forms.IDLE);
        setSelectedApplicationProfile(profile);
        console.log(`User ${userId} creating Session for ${appId} ${version}. Errors are expected as the stream updates.`);
        setConnectionText(`User ${userId} attempting to create streaming session...`);
        const createdStreamResponse = await createStreamingSession(streamServer, appId, version, profile);
        
        if (createdStreamResponse.status > 400) {
                console.log(`Failed to create a new streaming session for ${appId} ${version}. Error code ${createdStreamResponse.status}`);
                alert(`Failed to create a new streaming session for ${appId} ${version}. Error code ${createdStreamResponse.status}`)
                resetState();
                return;
            }
        
        const newSessionId = (createdStreamResponse.data as StreamItem).id;
        setSessionId(newSessionId);
        setStreamStatus(StreamStatus.INITIALIZING);
        setConnectionText(`User ${userId} attempting to load stream...`);
        if (createdStreamResponse.status === 202) {
            pollForSessionReady(newSessionId);
            return;
        }

        setupStream((createdStreamResponse.data as StreamItem));
    }, [streamServer, resetState, pollForSessionReady, setupStream, sessionId, endStream, userId]);

    /**
     * Button press for ending stream
     */
    const resetStream = useCallback(async () => {
        await endStream();
        resetState();
        safeTerminateStream();
    }, [resetState, endStream]);

    /**
     * Clean up session when stream fails
     */
    const cleanupSession = useCallback(async () => {
        if (sessionId) {
            try {
                await endStream();
                // Clear the session ID after successful cleanup
                setSessionId('');
            } catch (error) {
                console.warn('Failed to cleanup session:', error);
            }
        }
        safeTerminateStream();
    }, [sessionId, endStream]);
            
    return (
        <AppModeProvider>
            <div
            style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%'
            }}
            >


            { /* End Stream button */}
            {StreamConfig.source === "stream" &&
                <button className="nvidia-button"
                onClick={resetStream}
                type="button"
                aria-label={t('streaming.endStream')}
                style={{ position: "absolute", right: "15px", top:"8px", width: "250px", visibility: streamStatus === StreamStatus.INITIALIZING || streamStatus === StreamStatus.INITIALIZED? "visible": "hidden" }}
                >
                {t('streaming.endStream')}
                </button>
            }

            { /* Idle Form */}
            {currentForm === Forms.IDLE &&
                <div>
                    <div className="loading-indicator-label" aria-live="polite">
                        {connectionText}
                        <div
                            className="spinner-border"
                            role="status"
                            aria-label={connectionText || t('streaming.connecting')}
                            style={{ marginTop: 10, visibility: streamStatus === (StreamStatus.INITIALIZING) ? 'visible': 'hidden'}}
                        >
                            <span className="sr-only">{connectionText || t('streaming.connecting')}</span>
                        </div>
                    </div>
                </div>
            }


            { /* Stream URLs Form  */}
            {(currentForm === Forms.StreamURLs) &&
                <ServerURLsForm
                    appServer={appServer}
                    streamServer={streamServer}
                    onNext={(appServer, streamServer, applications) => {
                        setCurrentForm(Forms.Applications);
                        setAppServer(appServer);
                        setStreamServer(streamServer);
                        setApplications(applications);
                    }}
                    onBack={(appServer, streamServer) => {
                        setCurrentForm(Forms.StreamURLs);
                        setAppServer(appServer);
                        setStreamServer(streamServer);
                    }}
                />         
            }
                
            { /* Applications Form  */}
            {(currentForm === Forms.Applications) &&
                <ApplicationsForm
                appServer={appServer}
                applications={applications}
                onNext={(applicationId, versions) => {
                    setCurrentForm(Forms.Versions);
                    setSelectedApplicationId(applicationId);
                    setApplicationVersions(versions);
                }}
                onBack={() => {
                    setCurrentForm(Forms.StreamURLs);
                    setSelectedApplicationId('');
                    setApplicationVersions([]);
                }}
                />           
            }
                
            { /* Application Versions Form  */}
            {(currentForm === Forms.Versions) &&
                <VersionsForm
                appServer={appServer}
                applicationId={selectedApplicationId}
                versions={applicationVersions}
                onNext={(selectedVersion, profiles) => {
                    setCurrentForm(Forms.Profiles);
                    setSelectedApplicationVersion(selectedVersion);
                    setApplicationProfiles(profiles);
                }}
                onBack={() => {
                    setCurrentForm(Forms.Applications);
                    setSelectedApplicationVersion('');
                    setApplicationProfiles([]);
                }}
                />   
            }
                
            { /* Application Profiles Form  */}
            {(currentForm === Forms.Profiles) &&
                <ProfilesForm
                profiles={applicationProfiles}
                onNext={(selectedApplicationProfile) => startStream(selectedApplicationId, selectedApplicationVersion, selectedApplicationProfile)}
                onBack={() => {
                    setCurrentForm(Forms.Versions);
                    setSelectedApplicationProfile('');
                    setApplicationProfiles([]);
                }}
                />       
            }
                
            { /* Stream without UI Form  */}
            {(currentForm === Forms.Stream) &&
                <StreamOnlyWindow
                    sessionId={StreamConfig.source === "local" ? "" : sessionId}
                    backendUrl={StreamConfig.source === "local" ? "" : backendUrl}
                    signalingserver={signalingserver}
                    signalingport={signalingport}
                    mediaserver={mediaserver}
                    mediaport={mediaport}
                    accessToken={accessToken}
                    userId={userId}
                    onStreamFailed={cleanupSession}
                    isViewer={isViewer}
                />    
            }  
        </div>
        </AppModeProvider>
    );
};

export default App;


