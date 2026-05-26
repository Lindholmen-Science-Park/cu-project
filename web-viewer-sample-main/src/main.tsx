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

import './i18n';
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./app/App.tsx";
import "./app/index.css";

// Global console filter for verbose streaming library messages
const ENABLE_CONSOLE_FILTERING = true; // Set to false to see all messages

if (ENABLE_CONSOLE_FILTERING) {
    const originalConsoleLog = console.log;
    const originalConsoleInfo = console.info;
    
    const shouldFilterMessage = (args: any[]): boolean => {
        return args.some(arg => {
            if (typeof arg === 'string') {
                return arg.includes('"type":"info","title":"unknown","status":100') ||
                       (arg.includes('"detail":"{') && arg.includes('}##[')) ||
                       arg.includes('"detail":"{') && arg.includes('}","request":"message"') ||
                       // Filter movement message logs specifically
                       (arg.includes('"type":"info","title":"inProgress","status":100') && 
                        arg.includes('"detail":"Custom message being sent to the stream"') &&
                        arg.includes('"event_type":"movement"'));
            }
            if (typeof arg === 'object' && arg !== null) {
                const str = JSON.stringify(arg);
                return str.includes('"type":"info","title":"unknown","status":100') ||
                       (str.includes('"detail":"{') && str.includes('}##[')) ||
                       (str.includes('"detail":"{') && str.includes('}","request":"message"')) ||
                       // Filter movement message logs specifically
                       (str.includes('"type":"info","title":"inProgress","status":100') && 
                        str.includes('"detail":"Custom message being sent to the stream"') &&
                        str.includes('"event_type":"movement"'));
            }
            return false;
        });
    };
    
    console.log = (...args: any[]) => {
        if (!shouldFilterMessage(args)) {
            originalConsoleLog.apply(console, args);
        }
    };
    
    console.info = (...args: any[]) => {
        if (!shouldFilterMessage(args)) {
            originalConsoleInfo.apply(console, args);
        }
    };
}

ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>
);
