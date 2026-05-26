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
import React, { useState, useImperativeHandle, forwardRef } from "react";
import '../../app/App.css';
import './USDStage.css';


interface USDPrimType {
    name?: string;
    path: string;
    children?: USDPrimType[];
}

interface USDStageProps {
    width: number;
    usdPrims: USDPrimType[];
    selectedUSDPrims: Set<USDPrimType>;
    onSelectUSDPrims: (selectedUsdPrims: Set<USDPrimType>) => void;
    fillUSDPrim: (usdPrim: USDPrimType) => void;
    onReset: () => void;
}

const USDStage = forwardRef<{ resetExpandedIds: () => void }, USDStageProps>((props, ref) => {
    const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set<string>());
    
    /**
    * @function resetExpandedIds
    *
    * Public function for resetting the expanded state of the list.
    */
    const resetExpandedIds = (): void => {
        setExpandedIds(new Set<string>());
    };

    useImperativeHandle(ref, () => ({
        resetExpandedIds
    }));
    
    /**
    * @function toggleExpand
    *
    * Toggle the expanded states in the list.
    */
    const toggleExpand = (obj: USDPrimType, event: React.MouseEvent<HTMLSpanElement, MouseEvent>): void => {
        event.stopPropagation(); // Prevents the click from bubbling up to parent elements
        props.fillUSDPrim(obj);
        setExpandedIds(prevState => {
            const newExpandedIds = new Set(prevState); // Create a copy of the current Set
            if (newExpandedIds.has(obj.path)) {
                newExpandedIds.delete(obj.path); // Remove id if it's already expanded
            } else {
                newExpandedIds.add(obj.path); // Add id if it's not expanded
            }
            return newExpandedIds;
        });
    }
    
    /**
    * @function handleListClick
    *
    * Change state when list selection changes.
    */
    const handleListClick = (obj: USDPrimType, event: React.MouseEvent<HTMLDivElement, MouseEvent>): void => {
        event.stopPropagation();
        const newSelectedItems = new Set(props.selectedUSDPrims);
        if (newSelectedItems.has(obj)) {
            newSelectedItems.delete(obj); // Deselect if already selected
        } else {
            newSelectedItems.add(obj); // Add to selection if not already selected
        }
        props.onSelectUSDPrims(newSelectedItems);
    }
    
    /**
    * @function renderList
    *
    * Render the list.
    */
    const renderList = (usdPrims: USDPrimType[]): JSX.Element[] | undefined => {
        if (usdPrims === null || !Array.isArray(usdPrims)) {
            return;
        }
        return usdPrims.map((obj, index) => {
            const isLeaf = !obj.children || obj.children.length === 0;
            const isOpen = expandedIds.has(obj.path);
            const isSelected = props.selectedUSDPrims.has(obj);
            const listItemClass = `list-item ${isLeaf ? 'leaf' : 'parent'} ${isOpen ? 'open' : ''} ${isSelected ? 'selected' : ''}`;
            const itemContentClass = `item-content ${isLeaf ? 'leaf' : 'parent'} ${isOpen ? 'open' : ''} ${isSelected ? 'selected' : ''}`;
            const expandToggleClass = `expand-toggle ${isSelected ? 'selected' : 'deselected'}`;

            return (
                <li key={obj.name || index} className={listItemClass}>
                    <div className={itemContentClass} onClick={(e) => handleListClick(obj, e)}
                        tabIndex={0}
                    >
                        {!isLeaf && (
                            <span onClick={(e) => toggleExpand(obj, e)} className={expandToggleClass}>
                                {isOpen ? '▼' : '▶'}
                            </span>
                        )}
                        {obj.name}
                    </div>
                    {isOpen && !isLeaf && obj.children && (
                        <ul className="nested-list">
                            {renderList(obj.children)}
                        </ul>
                    )}
                </li>
            );
        });
    }

    const handleReset = () => {
        props.onReset();
    };

    return (
        <div className="usdStageContainer" style={{ width: props.width }}>
            <div className="usdStageHeader">
                {'USD Stage'}
                <button className="nvidia-button" onClick={handleReset}>Reset</button>
            </div>
            <ul className="list-container">
                {renderList(props.usdPrims)}
            </ul>
        </div>
    );
});

USDStage.displayName = 'USDStage';

export default USDStage;


