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
import React, { useState, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import '../../../app/App.css';
import AppStream from '../AppStream';
import StreamConfig from '../../../config/stream.config.json';
import { sendMessage } from '../messaging';
import USDAsset from "../../dev/usd/USDAsset";
import USDStage from "../../dev/usd/USDStage";
// Define headerHeight constant
const headerHeight = 60;


interface USDAssetType {
    name: string;
    url: string;
}

interface USDPrimType {
    name?: string;
    path: string;
    children?: USDPrimType[];
}

export interface AppProps {
    sessionId: string
    backendUrl: string
    signalingserver: string
    signalingport: number
    mediaserver: string
    mediaport: number
    accessToken: string
    userId?: string
    onStreamFailed: () => void;
    isViewer?: boolean;
}

interface AppStreamMessageType {
    event_type: string;
    payload: any;
}

const App: React.FC<AppProps> = (props) => {
    const { t } = useTranslation();
    const usdStageRef = useRef<{ resetExpandedIds: () => void }>(null);
    
    // list of selectable USD assets
    const usdAssets: USDAssetType[] = StreamConfig.source === "stream"? [
        {name: "Sample 1", url:"${omni.usd_viewer.samples}/samples_data/stage01.usd"},
        {name: "Sample 2", url:"${omni.usd_viewer.samples}/samples_data/stage02.usd"},
    ]
    :
    [
        {name: "Sample 1", url:"./samples/stage01.usd"},
        {name: "Sample 2", url:"./samples/stage02.usd"},
    ];

    const [selectedUSDAsset, setSelectedUSDAsset] = useState<USDAssetType>(usdAssets[0]);
    const [usdPrims, setUsdPrims] = useState<USDPrimType[]>([]);
    const [selectedUSDPrims, setSelectedUSDPrims] = useState<Set<USDPrimType>>(new Set<USDPrimType>());
    const [isKitReady, setIsKitReady] = useState(false);
    const [showStream, setShowStream] = useState(false);
    const [showUI, setShowUI] = useState(false);
    const [isLoading, setIsLoading] = useState(StreamConfig.source === "stream" ? true : false);
    const [loadingText, setLoadingText] = useState(
        StreamConfig.source === "gfn" ? t('loading.gfnLogin') : 
        (StreamConfig.source === "stream" ? t('loading.waitingForStream') : t('loading.waitingForStreamBegin'))
    );

    /**
    * @function queryLoadingState
    *
    * Sends Kit a message to find out what the loading state is.
    * Receives a 'loadingStateResponse' event type
    */
    const queryLoadingState = useCallback((): void => {
        const message: AppStreamMessageType = {
            event_type: "loadingStateQuery",
            payload: {}
        };
        sendMessage(message.event_type, message.payload);
    }, []);

    /**
     * @function onStreamStarted
     *
     * Sends a request to open an asset. If the stream is from GDN it is assumed that the
     * application will automatically load an asset on startup so a request to open a stage
     * is not sent. Instead, we wait for the streamed application to send a
     * openedStageResult message.
     */
    const onStreamStarted = useCallback((): void => {
        pollForKitReady()
    }, []);

    /**
    * @function pollForKitReady
    *
    * Attempts to query Kit's loading state until a response is received.
    * Once received, the 'isKitReady' flag is set to true and polling ends
    */
    const pollForKitReady = useCallback(async () => {
        if (isKitReady === true) return

        console.info("polling Kit availability")
        queryLoadingState()
        setTimeout(() => pollForKitReady(), 3000); // Poll every 3 seconds
    }, [isKitReady, queryLoadingState]);
    
    /**
     * @function getAsset
     * 
     * Attempts to retrieve an asset from the list of USD assets based on a supplied USD path
     * If a match is not found, a USDAssetType with empty values is returned.
     */
    const getAsset = useCallback((path: string): USDAssetType => {
        if (!path)
            return {name: "", url: ""}
        
        // returns the file name from a path
        const getFileNameFromPath = (path: string): string | undefined => path.split(/[/\\]/).pop();

        for (const asset of usdAssets) {
            if (getFileNameFromPath(asset.url) === getFileNameFromPath(path))
                return asset
        }
        
        return {name: "", url: ""}
    }, [usdAssets]);

    /**
    * @function onLoggedIn
    *
    * Runs when the user logs in
    */
    const onLoggedIn = useCallback((userId: string): void => {
        if (StreamConfig.source === "gfn"){
            console.info(`Logged in to GeForce NOW as ${userId}`)
            setLoadingText(t('loading.waitingForStreamBegin'));
            setIsLoading(false);
        }
    }, []);

    /**
    * @function openSelectedAsset
    *
    * Send a request to load an asset based on the currently selected asset
    */
    const openSelectedAsset = useCallback((): void => {
        setLoadingText(t('loading.loadingAsset'));
        setShowStream(false);
        setIsLoading(true);
        setUsdPrims([]);
        setSelectedUSDPrims(new Set<USDPrimType>());
        usdStageRef.current?.resetExpandedIds();
        console.log(`Sending request to open asset: ${selectedUSDAsset.url}.`);
        const message: AppStreamMessageType = {
            event_type: "openStageRequest",
            payload: {
                url: selectedUSDAsset.url
            }
        };
        sendMessage(message.event_type, message.payload);
    }, [selectedUSDAsset]);

    /**
    * @function onSelectUSDAsset
    *
    * React to user selecting an asset in the USDAsset selector.
    */
    const onSelectUSDAsset = useCallback((usdAsset: USDAssetType): void => {
        console.log(`Asset selected: ${usdAsset.name}.`);
        setSelectedUSDAsset(usdAsset);
        // Note: We'll call openSelectedAsset in a useEffect when selectedUSDAsset changes
    }, []);
    
    /**
    * @function getChildren
    *
    * Send a request for the child prims of the given usdPrim.
    * Note that a filter is supported.
    */
    const getChildren = useCallback((usdPrim: USDPrimType | null = null): void => {
        // Get geometry prims. If no usdPrim is specified then get children of /World.
        console.log(`Requesting children for path: ${usdPrim ? usdPrim.path : '/World'}.`);
        const message: AppStreamMessageType = {
            event_type: "getChildrenRequest",
            payload: {
                prim_path   : usdPrim ? usdPrim.path : '/World',
                filters     : ['USDGeom']
            }
        };
        sendMessage(message.event_type, message.payload);
    }, []);

    /**
    * @function makePickable
    *
    * Send a request to make prims pickable/selectable.
    * By default the client requests to make only a handful of the prims selectable - leaving the background items unselectable.
    */
    const makePickable = useCallback((usdPrims: USDPrimType[]): void => {
        const paths: string[] = usdPrims.map(prim => prim.path);
        console.log(`Sending request to make prims pickable: ${paths}.`);
        const message: AppStreamMessageType = {
            event_type: "makePrimsPickable",
            payload: {
                paths   : paths,
            }
        };
        sendMessage(message.event_type, message.payload);
    }, []);

    /**
    * @function onSelectUSDPrims
    *
    * React to user selecting items in the USDStage list.
    * Sends a request to change the selection in the USD Stage.
    */
    const onSelectUSDPrims = useCallback((selectedUsdPrims: Set<USDPrimType>): void => {
        console.log(`Sending request to select: ${selectedUsdPrims}.`);
        setSelectedUSDPrims(selectedUsdPrims);
        const paths: string[] = Array.from(selectedUsdPrims).map(obj => obj.path);
        const message: AppStreamMessageType = {
            event_type: "selectPrimsRequest",
            payload: {
                paths: paths
            }
        };
        sendMessage(message.event_type, message.payload);

        selectedUsdPrims.forEach(usdPrim => {onFillUSDPrim(usdPrim)});
    }, []);

    /**
    * @function onStageReset
    *
    * Clears the selection and sends a request to reset the stage to how it was at the time it loaded.
    */
    const onStageReset = useCallback((): void => {
        setSelectedUSDPrims(new Set<USDPrimType>());
        const selection_message: AppStreamMessageType = {
            event_type: "selectPrimsRequest",
            payload: {
                paths: []
            }
        };
        sendMessage(selection_message.event_type, selection_message.payload);

        const reset_message: AppStreamMessageType = {
            event_type: "resetStage",
            payload: {}
        };
        sendMessage(reset_message.event_type, reset_message.payload);
    }, []);

    /**
    * @function onFillUSDPrim
    *
    * If the usdPrim has a children property a request is sent for its children.
    * When the streaming app sends an empty children value it is not an array.
    * When a prim does not have children the streaming app does not provide a children
    * property to begin with.
    */
    const onFillUSDPrim = useCallback((usdPrim: USDPrimType): void => {
        if (usdPrim !== null && "children" in usdPrim && !Array.isArray(usdPrim.children)) {
            getChildren(usdPrim);
        }
    }, [getChildren]);
    
    /**
    * @function findUSDPrimByPath
    *
    * Recursive search for a USDPrimType object by path.
    */
    const findUSDPrimByPath = useCallback((path: string, array: USDPrimType[] = usdPrims): USDPrimType | null => {
        if (Array.isArray(array)) {
            for (const obj of array) {
                if (obj.path === path) {
                    return obj;
                }
                if (obj.children && obj.children.length > 0) {
                    const found = findUSDPrimByPath(path, obj.children);
                    if (found) {
                        return found;
                    }
                }
            }
        }
        return null;
    }, [usdPrims]);
    
    /**
    * @function handleCustomEvent
    *
    * Handle message from stream.
    */
    const handleCustomEvent = useCallback((event: any): void => {
        if (!event) {
            return;
        }

        // response received once a USD asset is fully loaded
        if (event.event_type === "openedStageResult") {
            if (event.payload.result === "success") {
                queryLoadingState() 
            }
            else {
                console.error('Kit App communicates there was an error loading: ' + event.payload.url);
            }
        }
        
        // response received from the 'loadingStateQuery' request
        else if (event.event_type == "loadingStateResponse") {
            // loadingStateRequest is used to poll Kit for proof of life.
            // For the first loadingStateResponse we set isKitReady to true
            // and run one more query to find out what the current loading state
            // is in Kit
            if (isKitReady === false) {
                console.info("Kit is ready to load assets")
                setIsKitReady(true)
                queryLoadingState()
            }
            
            else {
                const usdAsset: USDAssetType = getAsset(event.payload.url)
                const isStageValid: boolean = !!(usdAsset.name && usdAsset.url)
                
                // set the USD Asset dropdown to the currently opened stage if it doesn't match
                if (isStageValid && usdAsset !== undefined && selectedUSDAsset !== usdAsset)
                    setSelectedUSDAsset(usdAsset)

                // if the stage is empty, force-load the selected usd asset; the loading state is irrelevant
                if (!event.payload.url)
                    openSelectedAsset()
                
                // if a stage has been fully loaded and isn't a part of this application, force-load the selected stage
                else if (!isStageValid && event.payload.loading_state === "idle"){
                    console.log(`The loaded asset ${event.payload.url} is invalid.`)
                    openSelectedAsset()
                }
                
                // show stream and populate children if the stage is valid and it's done loading
                if (isStageValid && event.payload.loading_state === "idle")
                {
                    getChildren()
                    setShowStream(true);
                    setLoadingText(t('loading.assetLoaded'));
                    setShowUI(true);
                    setIsLoading(false);
                }
            }
        }
        
        // Loading progress amount notification.
        else if (event.event_type === "updateProgressAmount") {
            console.log('Kit App communicates progress amount.');
        }
            
        // Loading activity notification.
        else if (event.event_type === "updateProgressActivity") {
            console.log('Kit App communicates progress activity.');
            if (loadingText !== t('loading.loadingAsset'))
                setLoadingText(t('loading.loadingAsset'));
                setIsLoading(true);
        }
            
        // Notification from Kit about user changing the selection via the viewport.
        else if (event.event_type === "stageSelectionChanged") {
            console.log(event.payload.prims.constructor.name);
            if (!Array.isArray(event.payload.prims) || event.payload.prims.length === 0) {
                console.log('Kit App communicates an empty stage selection.');
                setSelectedUSDPrims(new Set<USDPrimType>());
            }
            else {
                console.log('Kit App communicates selection of a USDPrimType: ' + event.payload.prims.map((obj: any) => obj).join(', '));
                const usdPrimsToSelect: Set<USDPrimType> = new Set<USDPrimType>();
                event.payload.prims.forEach((obj: any) => {
                    const result = findUSDPrimByPath(obj);
                    if (result !== null) {
                        usdPrimsToSelect.add(result);
                    }
                });
                setSelectedUSDPrims(usdPrimsToSelect);
            }
        }
        // Streamed app provides children of a parent USDPrimType
        else if (event.event_type === "getChildrenResponse") {
            console.log('Kit App sent stage prims');
            const prim_path = event.payload.prim_path;
            const children = event.payload.children;
            const usdPrim = findUSDPrimByPath(prim_path);
            if (usdPrim === null) {
                setUsdPrims(children);
            }
            else {
                usdPrim.children = children;
                setUsdPrims(prevPrims => [...prevPrims]);
            }
            if (Array.isArray(children)){
                makePickable(children);
            }
        }
        // other messages from app to kit
        else if (event.messageRecipient === "kit") {
            console.log("onCustomEvent");
            console.log(JSON.parse(event.data).event_type);
        }
    }, [isKitReady, selectedUSDAsset, loadingText, queryLoadingState, getAsset, openSelectedAsset, getChildren, findUSDPrimByPath, makePickable]);

    
    const sidebarWidth = 300;
    return (
        <div
            style={{
                position: 'absolute',
                top: headerHeight,
                width: '100%',
                height: '100%'
            }}
        >
            <div style={{
                        position: 'absolute',
                        height: `calc(100% - ${headerHeight}px)`,
                        width: `calc(100% - ${sidebarWidth}px)`
            }}>
                
            {/* Loading text indicator */}
            {!showStream && 
                <div className="loading-indicator-label">
                    {loadingText}
                    <div className="spinner-border" role="status" style={{ marginTop: 10, visibility: isLoading? 'visible': 'hidden' }} />
                </div>
            }

            {/* Streamed app */}
            <AppStream
                sessionId={props.sessionId}
                backendUrl={props.backendUrl}
                signalingserver={props.signalingserver}
                signalingport={props.signalingport}
                mediaserver={props.mediaserver}
                mediaport={props.mediaport}
                accessToken={props.accessToken}
                onStarted={onStreamStarted}
                style={{
                    position: 'relative',
                    visibility: showStream? 'visible' : 'hidden'
                }}
                onLoggedIn={onLoggedIn}
                handleCustomEvent={handleCustomEvent}
                onStreamFailed={props.onStreamFailed}
                markerPlacementEnabled={false}
                pointClickEnabled={false}
                />
            </div>

            {showUI &&
            <>
                    
                {/* USD Asset Selector */}
                <USDAsset
                    usdAssets={usdAssets}
                    selectedAssetUrl={selectedUSDAsset?.url}
                    onSelectUSDAsset={onSelectUSDAsset}
                    width={sidebarWidth}
                />
                {/* USD Stage Listing */}
                <USDStage
                    ref={usdStageRef}
                    width={sidebarWidth}
                    usdPrims={usdPrims}
                    onSelectUSDPrims={onSelectUSDPrims}
                    selectedUSDPrims={selectedUSDPrims}
                    fillUSDPrim={onFillUSDPrim}
                    onReset={onStageReset}
                    />
                </>
            }
        </div>
        );
};

export default App;
