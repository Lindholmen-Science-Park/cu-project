#!/usr/bin/env python3
"""
Auto-load script for USD Composer to load a scene on startup.
This script is executed when USD Composer starts up via the --exec flag.
Behavior:
- If environment variable YOUNITE_SCENE_NAME is set, tries to open that scene
  from source/data/scenes or source/data/Assets/Elevator (adds .usda if missing).
- Otherwise opens source/data/scenes/main_scene.usda by default.
"""

import asyncio
import omni.usd
import omni.kit.app
import os
from pathlib import Path

async def open_mastah_stage():
    """Open the desired scene file automatically on startup."""
    try:
        # Wait for the USD context to be ready
        await omni.kit.app.get_app().next_update_async()
        
        # Get the USD context
        usd_context = omni.usd.get_context()
        
        # Construct the path to mastah.usda relative to this script
        script_dir = Path(__file__).parent
        scenes_dir = script_dir / "source" / "data" / "scenes"
        elevator_test_dir = script_dir / "source" / "data" / "Assets" / "Elevator"

        def resolve_scene_path(scene_name: str):
            if not scene_name.lower().endswith(".usda"):
                scene_name = f"{scene_name}.usda"
            for folder in (scenes_dir, elevator_test_dir):
                path = (folder / scene_name).resolve()
                if path.exists():
                    return path
            return (scenes_dir / scene_name).resolve()

        # Determine desired scene from environment variable (if provided)
        desired_scene_name = os.environ.get("YOUNITE_SCENE_NAME", "").strip()
        if desired_scene_name:
            candidate_path = resolve_scene_path(desired_scene_name)
        else:
            candidate_path = None

        # Default scene path
        default_scene_path = (scenes_dir / "main_scene.usda").resolve()
        
        # Choose which scene to open
        if candidate_path and candidate_path.exists():
            scene_path = candidate_path
            print(f"Auto-loading requested scene from env YOUNITE_SCENE_NAME: {scene_path}")
        else:
            if candidate_path and not candidate_path.exists():
                print(f"WARNING: Requested scene not found: {candidate_path}. Falling back to default scene.")
            scene_path = default_scene_path
            print(f"Auto-loading default scene: {scene_path}")
        
        # Check if file exists
        if not scene_path.exists():
            print(f"ERROR: USD file not found at {scene_path}")
            return False
            
        # Wait a bit more for the context to be fully ready
        await asyncio.sleep(1.0)
        
        # Open the stage asynchronously
        result, error = await usd_context.open_stage_async(
            str(scene_path), 
            load_set=omni.usd.UsdContextInitialLoadSet.LOAD_ALL
        )
        
        if error:
            print(f"ERROR: Failed to open stage: {error}")
            return False
        else:
            print(f"SUCCESS: Scene loaded automatically: {scene_path.name}")
            return True
            
    except Exception as e:
        print(f"ERROR: Exception occurred while loading scene: {e}")
        return False

# Schedule the async function to run
asyncio.ensure_future(open_mastah_stage())
