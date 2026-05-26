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

import React, { useState } from 'react';
import { getApplications, getApplicationVersions, getApplicationVersionProfiles } from './Endpoints';

const nextButtonStyle = {
    width: '200px',
    margin: '20px 15px 0px 0px',
};

const formContainerStyle = {
    margin: '20px 20px',
}

export interface Application {
    id: string
    name: string
    version?: string
    profile?: string
}


interface ServerURLsProps {
    onBack: (appServer: string, streamServer: string) => void;
    onNext: (appServer: string, streamServer: string, applications: Application[]) => void;
    appServer: string
    streamServer: string
}


interface ApplicationsProps {
    onBack: () => void;
    onNext: (applicationId: string, versions: string[]) => void;
    appServer: string,
    applications: Application[];
}


interface VersionsProps {
    onBack: () => void;
    onNext: (selectedVersion: string, profiles: string[]) => void;
    appServer: string;
    applicationId: string;
    versions: string[];
}


interface ProfilesProps {
    onBack: () => void;
    onNext: (applicationProfile: string) => void;
    profiles: string[];
}




/**
* Form that contains the URLs for streaming
*/
export const ServerURLsForm: React.FC<ServerURLsProps> = ({ appServer: initialAppServer, streamServer: initialStreamServer, onBack, onNext }) => {
    const [appServer, setAppServer] = useState(initialAppServer);
    const [streamServer, setStreamServer] = useState(initialStreamServer);
    const [applications, setApplications] = useState<Application[]>([]);

    const handleBack = (): void => {
        const appServerValue = (document.getElementById("app-server") as HTMLInputElement).value;
        const streamServerValue = (document.getElementById("stream-server") as HTMLInputElement).value;
        setAppServer(appServerValue);
        setStreamServer(streamServerValue);
        onBack(appServerValue, streamServerValue);
    }

    /**
     * Validation procedure for user-entered endpoints
     * 
     * @param endpoint - The endpoint URL
     * @returns true if validation succeeded, otherwise false
     */
    const validateEndpoint = async (endpoint: string): Promise<boolean> => {
        try {
            const response = await fetch(endpoint, {
            method: 'GET',
            mode: 'cors',
            headers: {'Content-Type': 'application/json'},
            });
    
            if (!response.ok) {
                alert(`Error: Received status code ${response.status}`);
                return false
            }
        }
        
        catch (error) {
            alert(`Error: Failed to connect to endpoint \`${endpoint}\``);
            return false
        }

        return true
    }

    /**
     * Executes when the 'next' button is clicked.
     */
    const handleNext = async () => {
        const appServerValue = (document.getElementById("app-server") as HTMLInputElement).value;
        
        // validate app server URL value is entered
        if (appServerValue.length === 0) {
            alert("An App Server must be entered.")
            return
        }

        // validate app server URL formatting
        try {
            new URL(appServerValue);
        }
        catch (err) {
            alert(`Invalid App Server URL format`);
            return;
        }
        
        // validate connection can be made to app server
        if  (!await validateEndpoint(`${appServerValue}/cfg/apps`)) return
        
        const streamServerValue = (document.getElementById("stream-server") as HTMLInputElement).value;
        if (streamServerValue.length === 0) {
            alert("A Stream Server must be entered.")
            return
        }
        
        // validate stream server URL formatting
        try {
            new URL(streamServerValue);
        }
        catch (err) {
            alert(`Invalid Stream Server URL format`);
            return;
        }

        // validate connection can be made to stream server
        if  (!await validateEndpoint(`${streamServerValue}/streaming/stream`)) return

        await loadApplications(appServerValue)
        
        // validate that applications exist
        if (applications.length === 0) {
            alert(`No applications were found from App Server \`${appServerValue}\``)
        }
        else {
            onNext(appServerValue, streamServerValue, applications)
        }
    }

    const loadApplications = async (appServerValue: string) => {
        const response = await getApplications(appServerValue);
        if (response.status === 200) {
            console.log(response.data)
            setApplications(Object.values(response.data));
        }
    };

    return (
        <div style={formContainerStyle}>
            <h3>Server Information</h3>
            <div className="mb-3">
            <div className="row align-items-center">

            <div className="container">
            <div className="row align-items-center mb-3">
                <div className="col-auto">
                <label htmlFor="input1" className="col-form-label">App Server</label>
                </div>
                <div className="col">
                    <input type="text" className="form-control" id="app-server" placeholder="Enter App Server" defaultValue={appServer} style={{outline:"2px solid #76b900"}} />
                </div>
            </div>

            <div className="row align-items-center">
                <div className="col-auto">
                <label htmlFor="input2" className="col-form-label">Stream Server</label>
                </div>
                <div className="col">
                <input type="text" className="form-control" id="stream-server" placeholder="Enter Stream Server" defaultValue={streamServer}  style={{outline:"2px solid #76b900"}} />
                </div>
            </div>
            </div>
            
            </div>
                <button type="button" className="nvidia-button" onClick={handleBack} style={nextButtonStyle}>Previous</button>
                <button type="button" className="nvidia-button" onClick={handleNext} style={nextButtonStyle}>Next</button>
            </div>
    </div>
    );
};

/**
* Form that allows a user to select an application
*/
export const ApplicationsForm: React.FC<ApplicationsProps> = ({ appServer, applications, onNext, onBack }) => {
    const [selectedApplication, setSelectedApplication] = useState<Application>(applications[0]);
    const [versions, setVersions] = useState<string[]>([]);

    /**
     * Executes when the 'next' button is clicked.
     */
    const handleNext = async () => {
        const selectedAppId: string = selectedApplication.id

        await loadVersions(appServer, selectedAppId)
        if (versions.length === 0) {
            alert(`No versions were found from Application with id ${selectedAppId}`)
            return
        }
        else {
            onNext(selectedApplication.id, versions)
        }
    }
    
    /**
     * Queries available application versions for the provided app server and app id
     * 
     * @param appServer - The app server URL
     * @param appId - The application id
     */
    const loadVersions = async (appServerValue: string, appId: string) => {
        const response = await getApplicationVersions(appServerValue, appId);
        if (response.status === 200) {
            setVersions(response.data.versions);
        }
    };
    
    /**
     * Executes when a user selects an application item from the dropdown
     */
    const handleSelectChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const selectedAppId = event.target.value;
        const foundApplication = applications.find((app) => app.id === selectedAppId);

        if (!foundApplication)
            throw new Error(`Application with id ${selectedAppId} not found`);

        setSelectedApplication(foundApplication);
    };

    return (
        <div style={formContainerStyle}>
            <h3>Select Application</h3>
            <div className="mb-3">
                <select
                    className="nvidia-dropdown"
                    id="exampleSelect"
                    value={selectedApplication.id} 
                    onChange={handleSelectChange}
                >
                        {applications.map((app) => (
                    <option key={app.id} value={app.id} className="nvidia-dropdown-option">
                        {app.id}
                    </option>
                    ))}
                    </select>
            </div>
                <button type="button" className="nvidia-button" onClick={onBack} style={nextButtonStyle}>Previous</button>
                <button type="button" className="nvidia-button" onClick={handleNext} style={nextButtonStyle}>Next</button>
            </div>
        );
};

/**
* Form that allows a user to select an application version
*/
export const VersionsForm: React.FC<VersionsProps> = ({ appServer, applicationId, versions, onNext, onBack }) => {
    const [selectedVersion, setSelectedVersion] = useState<string>(versions[0]);
    const [profiles, setProfiles] = useState<string[]>([]);

    /**
     * Executes when the 'next' button is clicked.
     */
    const handleNext = async () => {
        await loadProfiles(applicationId, selectedVersion)

        if (profiles.length === 0) {
            alert(`No profiles were found for Application version ${selectedVersion}`)
            return
        }
        else {
            onNext(selectedVersion, profiles)
        }
    }

    /**
     * Queries available profiles versions for the provided app id and version
     * 
     * @param appServer - The app server URL
     * @param appId - The application id
     */
    const loadProfiles = async (appId: string, version: string) => {
        const response = await getApplicationVersionProfiles(appServer, appId, version);
        if (response.status === 200) {
            setProfiles(response.data.profiles.map(p => p.id));
        }
    };

    /**
     * Executes when a user selects a version item from the dropdown
     */
    const handleSelectChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const selectedVersionValue = event.target.value;
        setSelectedVersion(selectedVersionValue);
    };


    return (
        <div style={formContainerStyle}>
            <h3>Select Version</h3>
            <div className="mb-3">
                <select
                    className="nvidia-dropdown"
                    id="exampleSelect"
                    value={selectedVersion} 
                    onChange={handleSelectChange}
                >
                        {versions.map((version) => (
                    <option key={version} value={version} className="nvidia-dropdown-option">
                        {version}
                    </option>
                    ))}
                    </select>
            </div>      
                <button type="button" className="nvidia-button" onClick={onBack} style={nextButtonStyle}>Previous</button>
                <button type="button" className="nvidia-button" onClick={handleNext} style={nextButtonStyle}>Next</button>
            </div>
        );
};

/**
* Form that allows a user to select an application profile
*/
export const ProfilesForm: React.FC<ProfilesProps> = ({ profiles, onNext, onBack }) => {
    const [selectedProfile, setSelectedProfile] = useState<string>(profiles[0]);

    /**
     * Executes when the 'next' button is clicked.
     */
    const handleNext = async () => {
        onNext(selectedProfile)
    }

    /**
     * Executes when a user selects a profile item from the dropdown
     */
    const handleSelectChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const selectedProfileValue = event.target.value;
        setSelectedProfile(selectedProfileValue);
    };

    return (
        <div style={formContainerStyle}>
            <h3>Select Profile</h3>
            <div className="mb-3">
                <select
                    className="nvidia-dropdown"
                    id="profileSelect"
                    value={selectedProfile} 
                    onChange={handleSelectChange}
                >
                        {profiles.map((profile) => (
                    <option key={profile} value={profile} className="nvidia-dropdown-option">
                        {profile}
                    </option>
                    ))}
                    </select>
            </div>
                <button type="button" className="nvidia-button" onClick={onBack} style={nextButtonStyle}>Previous</button>
                <button type="button" className="nvidia-button" onClick={handleNext} style={nextButtonStyle}>Next</button>
            </div>
        );
};
