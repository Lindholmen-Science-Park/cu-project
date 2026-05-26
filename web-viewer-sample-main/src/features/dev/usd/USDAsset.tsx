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

import React, { useState, useEffect } from "react";
import '../../app/App.css';
import './USDAsset.css';


interface USDAssetProps {
    width: number;
    usdAssets: { name: string; url: string }[];
    selectedAssetUrl?: string;
    onSelectUSDAsset: (asset: { name: string; url: string }) => void;
}

const USDAsset: React.FC<USDAssetProps> = ({ width, usdAssets, selectedAssetUrl, onSelectUSDAsset }) => {
    const findAssetIndexByUrl = (url?: string): number => {
        return usdAssets.findIndex(asset => asset.url === url);
    };

    const [selectedUSDAssetIndex, setSelectedUSDAssetIndex] = useState<number | null>(findAssetIndexByUrl(selectedAssetUrl));
    
    /**
    * @function handleSelectChange
    *
    * Handle selection in list.
    */
    const handleSelectChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const selectedIndex = parseInt(event.target.value, 10);
        setSelectedUSDAssetIndex(selectedIndex);
        if (onSelectUSDAsset) {
            onSelectUSDAsset(usdAssets[selectedIndex]);
        }
    };
    
    /**
    * Update state if the selectedAssetUrl prop changes.
    */
    useEffect(() => {
        const newIndex = findAssetIndexByUrl(selectedAssetUrl);
        if (newIndex !== selectedUSDAssetIndex) {
            setSelectedUSDAssetIndex(newIndex);
        }
    }, [selectedAssetUrl, selectedUSDAssetIndex]);
    
    /**
    * @function renderSelector
    *
    * Render the selector.
    */
    const renderSelector = (): JSX.Element => {
          const options = usdAssets.map((asset, index) => (
              <option key={index} value={index} className="usdAssetOption">
                  {asset.name}
              </option>
          ));

          return (
              <select
                  className="nvidia-dropdown"
                  onChange={handleSelectChange}
                  value={selectedUSDAssetIndex || ''}>
                  {options}
              </select>
          );
    }
    
    return (
          <div className="usdAssetContainer" style={{ width: width }}>
              <div className="usdAssetHeader">
                  {'USD Asset'}
              </div>
              <div className="usdAssetSelectorContainer">
                  {renderSelector()}
              </div>
          </div>
      );
};

export default USDAsset;


