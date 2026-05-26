"""
Waypoint Customization Extension

This extension demonstrates how to:
1. Access waypoint properties (comment, thumbnail, created_by, etc.)
2. Display tooltips/hover information
3. Add custom UI elements to waypoints
4. Create custom interaction buttons

Based on omni.kit.waypoint.core documentation:
https://docs.omniverse.nvidia.com/kit/docs/omni.kit.waypoint.core/latest/
"""

import asyncio
import base64
import carb
import sys
import omni.ext
import omni.kit.app
import omni.ui as ui
import omni.usd
import carb.input
from omni.kit.waypoint.core import ViewportWaypoint, get_instance
try:
    from omni.kit.waypoint.core import WaypointDelegate
    HAS_DELEGATE = True
except ImportError:
    HAS_DELEGATE = False
    WaypointDelegate = None
import functools
from pxr import Gf, UsdGeom

# Force output to be unbuffered
print("[Waypoint Extension] Module loaded", flush=True)
sys.stdout.flush()


class WaypointCustomizationManager:
    """Extension for customizing waypoint display and interactions"""

    def __init__(self):
        """Initialize the extension"""
        self._usd_context = None
        self._waypoint_manager = None
        self._subscription = None
        self._selection_subscription = None
        
        # Store custom waypoint data
        self._waypoint_data = {}
        self._waypoint_paths = []  # List of waypoint paths for quick lookup
        self._viewport_waypoints = {}  # Store ViewportWaypoint instances
        self._thumbnail_providers = {}  # Store in-memory image providers for thumbnails
        self._pending_recall = None  # Store pending recall operation for "Go There" button
        self._viewport_hover_subscription = None  # Viewport hover event subscription
        self._last_hovered_waypoint = None  # Track last hovered waypoint to avoid duplicate logs
        self._mouse_input_sub = None  # Subscription for mouse input events
        self._waypoint_screen_positions = {}  # Cache waypoint screen positions: path -> (x_px, y_px, in_view)
        self._update_subscription = None  # Subscription for update events to project waypoints
        
        # UI components
        self._tooltip_window = None
        self._tooltip_label = None
        self._waypoint_browser_window = None
        self._current_hovered_waypoint = None
        self._waypoint_popup = None  # Popup dialog for waypoint info
        
        # Initialize after a delay to ensure waypoint system is ready
        asyncio.ensure_future(self._initialize())

    async def _initialize(self):
        """Initialize the extension after startup"""
        print("[Waypoint Extension] Starting initialization...", flush=True)
        sys.stdout.flush()
        
        # Wait for USD context to be ready
        for _ in range(10):
            await omni.kit.app.get_app().next_update_async()
        
        try:
            # Get USD context
            self._usd_context = omni.usd.get_context()
            print("[Waypoint Extension] USD context obtained", flush=True)
            sys.stdout.flush()
            
            # Get waypoint manager instance
            try:
                self._waypoint_manager = get_instance()
                print(f"[Waypoint Extension] Waypoint manager: {self._waypoint_manager}", flush=True)
                
                # Monkey-patch ViewportWaypoint.recall to intercept navigation for our waypoints
                # Note: This is necessary because icon_click approach doesn't work with existing instances
                # We only intercept waypoints under /Viewport_Waypoints/
                manager_instance = self
                
                # Try to patch hover-related methods in ViewportWaypoint
                # Check if there are methods that get called on hover
                manager_instance = self
                
                # Debug: List all methods in ViewportWaypoint to find hover-related ones
                try:
                    all_methods = [m for m in dir(ViewportWaypoint) if not m.startswith('__') and callable(getattr(ViewportWaypoint, m, None))]
                    hover_related = [m for m in all_methods if 'hover' in m.lower() or 'tooltip' in m.lower() or 'mouse' in m.lower()]
                    if hover_related:
                        print(f"[Waypoint Extension] Found potential hover methods: {hover_related}", flush=True)
                        sys.stdout.flush()
                    else:
                        # Print first 20 methods to see what's available
                        print(f"[Waypoint Extension] No hover-related methods found. Sample ViewportWaypoint methods: {all_methods[:20]}", flush=True)
                        sys.stdout.flush()
                except Exception as e:
                    print(f"[Waypoint Extension] Could not inspect ViewportWaypoint methods: {e}", flush=True)
                    sys.stdout.flush()
                
                # Try to find and patch tooltip or hover methods
                potential_hover_methods = ['show_tooltip', '_show_tooltip', 'on_hover', '_on_hover', 
                                          'update_tooltip', '_update_tooltip', 'get_tooltip', '_get_tooltip',
                                          'on_mouse_over', '_on_mouse_over', 'handle_hover', '_handle_hover']
                
                hover_method_found = False
                for method_name in potential_hover_methods:
                    if hasattr(ViewportWaypoint, method_name):
                        original_method = getattr(ViewportWaypoint, method_name)
                        if not hasattr(ViewportWaypoint, f'_original_{method_name}'):
                            setattr(ViewportWaypoint, f'_original_{method_name}', original_method)
                            
                            def make_hover_wrapper(method_name, original):
                                @functools.wraps(original)
                                def hover_wrapper(self_instance, *args, **kwargs):
                                    waypoint_path = self_instance.path if hasattr(self_instance, 'path') else None
                                    if waypoint_path and waypoint_path.startswith("/Viewport_Waypoints/"):
                                        manager_instance._on_waypoint_hover(waypoint_path)
                                    return original(self_instance, *args, **kwargs)
                                return hover_wrapper
                            
                            setattr(ViewportWaypoint, method_name, make_hover_wrapper(method_name, original_method))
                            print(f"[Waypoint Extension] ✅ Patched {method_name} for hover detection", flush=True)
                            sys.stdout.flush()
                            hover_method_found = True
                            break
                
                if not hover_method_found:
                    print("[Waypoint Extension] ⚠️ No hover methods found to patch", flush=True)
                    print("[Waypoint Extension] Note: Waypoint icons are 3D gizmos - hover detection requires viewport mouse events", flush=True)
                    print("[Waypoint Extension] For now, logging will occur on click (recall) - true hover detection not available via API", flush=True)
                    sys.stdout.flush()
                    
                    # As a workaround, add logging to recall to show when waypoints are interacted with
                    # This is the closest we can get to hover detection with the available API
                    print("[Waypoint Extension] ⚠️ Hover logging will only occur on waypoint click (when recall is called)", flush=True)
                    sys.stdout.flush()
                
                if not hasattr(ViewportWaypoint, '_original_recall'):
                    ViewportWaypoint._original_recall = ViewportWaypoint.recall
                    print("[Waypoint Extension] Stored original recall method", flush=True)
                    sys.stdout.flush()
                    
                    @functools.wraps(ViewportWaypoint.recall)
                    def wrapped_recall(self_instance, without_camera=False, enable_settings=None, disable_settings=None):
                        """Intercept recall for waypoints under /Viewport_Waypoints/ to show popup"""
                        waypoint_path = self_instance.path
                        
                        # Only intercept our waypoints (those under /Viewport_Waypoints/)
                        if waypoint_path.startswith("/Viewport_Waypoints/"):
                            # This is called on click - don't log hover here, only log the click
                            print(f"[Waypoint Extension] 🔵 RECALL intercepted for waypoint: {waypoint_path}", flush=True)
                            sys.stdout.flush()
                            
                            # Try to load waypoint data if not already loaded
                            if waypoint_path not in manager_instance._waypoint_data:
                                try:
                                    stage = manager_instance._usd_context.get_stage()
                                    if stage:
                                        waypoint_prim = stage.GetPrimAtPath(waypoint_path)
                                        if waypoint_prim and waypoint_prim.IsValid():
                                            manager_instance._process_waypoint(waypoint_prim)
                                            if waypoint_path not in manager_instance._waypoint_paths:
                                                manager_instance._waypoint_paths.append(waypoint_path)
                                except Exception as load_error:
                                    print(f"[Waypoint Extension] Could not load waypoint on-the-fly: {load_error}", flush=True)
                            
                            # Show popup instead of navigating
                            manager_instance._show_waypoint_popup(waypoint_path)
                            
                            # Store the recall parameters for "Go There" button
                            manager_instance._pending_recall = {
                                'waypoint_path': waypoint_path,
                                'without_camera': without_camera,
                                'enable_settings': enable_settings,
                                'disable_settings': disable_settings,
                                'viewport_waypoint': self_instance
                            }
                            return  # Don't navigate - wait for user to click "Go There"
                        
                        # Not our waypoint - use original behavior
                        return ViewportWaypoint._original_recall(self_instance, without_camera, enable_settings, disable_settings)
                    
                    ViewportWaypoint.recall = wrapped_recall
                    print("[Waypoint Extension] ✅ Patched ViewportWaypoint.recall to intercept navigation", flush=True)
                    sys.stdout.flush()
                
                # Load waypoints immediately if stage is available
                stage = self._usd_context.get_stage()
                if stage:
                    print("[Waypoint Extension] Stage available, loading waypoints immediately...", flush=True)
                    sys.stdout.flush()
                    asyncio.ensure_future(self._load_waypoints())
                    
            except Exception as e:
                print(f"[Waypoint Extension] WARNING: Could not get waypoint manager: {e}", flush=True)
                self._waypoint_manager = None
                import traceback
                traceback.print_exc()
                sys.stdout.flush()
            sys.stdout.flush()
            
            # Subscribe to waypoint changes
            self._subscribe_to_waypoints()
            
            # Subscribe to stage changes
            import carb.eventdispatcher
            ed = carb.eventdispatcher.get_eventdispatcher()
            self._stage_event_observer = ed.observe_event(
                observer_name="younite.waypoint_customization_extension/stage_events",
                event_name="omni.usd@stage_event",
                on_event=self._on_stage_event,
                order=0,
            )
            
            # Subscribe to viewport mouse events for hover detection
            self._subscribe_to_viewport_hover()
            
            # Subscribe to selection changes to detect hover/selection of waypoints
            self._selection_subscription = ed.observe_event(
                observer_name="younite.waypoint_customization_extension/hover_detection",
                event_name="omni.usd@stage_event",
                on_event=self._on_selection_changed_for_hover,
                order=0,
            )
            
            # Note: We don't subscribe to selection changes for click handling - we use recall interception
            print("[Waypoint Extension] Subscribed to stage events, viewport hover, and selection changes", flush=True)
            sys.stdout.flush()
            
            # Check if stage is already open and load waypoints immediately
            stage = self._usd_context.get_stage()
            if stage:
                print(f"[Waypoint Extension] Stage already open: {stage}", flush=True)
                sys.stdout.flush()
                asyncio.ensure_future(self._load_waypoints())
            else:
                print("[Waypoint Extension] Stage not yet open, waiting for stage opened event", flush=True)
                sys.stdout.flush()
            
            print("[Waypoint Extension] Initialization complete", flush=True)
            sys.stdout.flush()
            
            # Create UI windows after initialization
            # Wait a bit for the stage to be fully ready
            await asyncio.sleep(0.5)
            self._create_waypoint_browser()
            
        except Exception as e:
            print(f"[Waypoint Extension] ERROR initializing: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()

    def _subscribe_to_waypoints(self):
        """Subscribe to waypoint events"""
        # This would be done through the waypoint manager API
        # The exact API depends on the waypoint extension implementation
        pass
    
    def _subscribe_to_viewport_hover(self):
        """Subscribe to viewport mouse events to detect hover over waypoint icons"""
        try:
            # Start hover monitoring after viewport is ready
            async def start_hover_monitoring():
                await asyncio.sleep(2.0)  # Wait for viewport to initialize
                
                try:
                    from omni.kit.viewport.utility import get_active_viewport_window
                    import omni.kit.viewport
                    
                    # Try to hook into waypoint manager's hover/tooltip system
                    # The waypoint manager might have internal hover tracking we can access
                    try:
                        waypoint_manager = self._waypoint_manager
                        if waypoint_manager:
                            # Try to access viewport waypoints and see if they have hover state
                            # Or try to patch a hover-related method if it exists
                            print("[Waypoint Extension] Waypoint manager available, checking for hover hooks...", flush=True)
                            sys.stdout.flush()
                            
                            # Check if waypoint manager has viewport waypoints we can monitor
                            if hasattr(waypoint_manager, '_viewport_waypoints'):
                                vp_waypoints = waypoint_manager._viewport_waypoints
                                print(f"[Waypoint Extension] Found {len(vp_waypoints) if vp_waypoints else 0} viewport waypoints", flush=True)
                                sys.stdout.flush()
                            
                            # Try to find and patch a hover handler if it exists
                            # This is a shot in the dark, but worth trying
                            if hasattr(waypoint_manager, '_on_icon_hover') or hasattr(waypoint_manager, '_handle_hover'):
                                print("[Waypoint Extension] Found potential hover handler in waypoint manager", flush=True)
                                sys.stdout.flush()
                    except Exception as e:
                        print(f"[Waypoint Extension] Could not inspect waypoint manager: {e}", flush=True)
                        sys.stdout.flush()
                    
                    # Since ViewportWaypoint has no hover methods and waypoint icons are 3D gizmos,
                    # hover detection is challenging. For now, let's try a workaround:
                    # Hook into the waypoint manager's delegate system or monitor when waypoints are "active"
                    
                    # Capture self for closure
                    manager_self = self
                    
                    # Implement hover detection using the recommended pattern:
                    # Project waypoint world positions to screen coordinates and check mouse proximity
                    manager_self._setup_waypoint_hover_detection()
                    
                    # Also try to hook into viewport window mouse events directly
                    try:
                        # Try to access viewport window's mouse event system
                        viewport_window = get_active_viewport_window()
                        if viewport_window and hasattr(viewport_window, '_window'):
                            window = viewport_window._window
                            # If window has mouse event callbacks, we could subscribe here
                            pass
                    except:
                        pass
                    
                    print("[Waypoint Extension] ✅ Hover monitoring started", flush=True)
                    sys.stdout.flush()
                    
                except Exception as e:
                    print(f"[Waypoint Extension] Could not set up viewport hover: {e}", flush=True)
                    sys.stdout.flush()
            
            asyncio.ensure_future(start_hover_monitoring())
            
            # Also try to use viewport interaction/selection events as a proxy
            # When a waypoint is selected or hovered, we can detect it
            print("[Waypoint Extension] ✅ Hover detection subscription started", flush=True)
            sys.stdout.flush()
                
        except Exception as e:
            print(f"[Waypoint Extension] Could not set up viewport hover detection: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
    
    def _on_waypoint_hover(self, waypoint_path: str):
        """Handle hover over a waypoint icon - log to console"""
        try:
            # Only log if this is a different waypoint than last time
            if waypoint_path != self._last_hovered_waypoint:
                waypoint_data = self._waypoint_data.get(waypoint_path, {})
                waypoint_name = waypoint_data.get('name', waypoint_path.split('/')[-1])
                comment = waypoint_data.get('comment', '')
                
                print(f"[Waypoint Extension] 🖱️ HOVERING over waypoint: {waypoint_name} ({waypoint_path})", flush=True)
                if comment:
                    print(f"  Comment: {comment}", flush=True)
                sys.stdout.flush()
                
                self._last_hovered_waypoint = waypoint_path
                
        except Exception as e:
            print(f"[Waypoint Extension] Error in hover handler: {e}", flush=True)
            sys.stdout.flush()
    
    def _on_waypoint_hover_exit(self):
        """Handle mouse leaving waypoint icon"""
        if self._last_hovered_waypoint:
            waypoint_data = self._waypoint_data.get(self._last_hovered_waypoint, {})
            waypoint_name = waypoint_data.get('name', self._last_hovered_waypoint.split('/')[-1])
            print(f"[Waypoint Extension] 🖱️ No longer hovering over waypoint: {waypoint_name}", flush=True)
            sys.stdout.flush()
            self._last_hovered_waypoint = None
    
    def _world_to_screen(self, world_pos: Gf.Vec3d, viewport_api) -> tuple:
        """Project world position to screen coordinates (pixels) and check if in view"""
        try:
            from omni.kit.viewport.utility import get_active_viewport
            from pxr import UsdGeom
            
            # Get viewport camera
            camera_path = viewport_api.camera_path if hasattr(viewport_api, 'camera_path') else None
            if not camera_path:
                return None, None, False
            
            # Get camera prim
            stage = self._usd_context.get_stage()
            if not stage:
                return None, None, False
            
            camera_prim = stage.GetPrimAtPath(camera_path)
            if not camera_prim or not camera_prim.IsValid():
                return None, None, False
            
            # Get camera transform
            camera = UsdGeom.Camera(camera_prim)
            xform = UsdGeom.Xformable(camera_prim)
            world_to_camera = xform.ComputeLocalToWorldTransform(0).GetInverse()
            
            # Transform world point to camera space
            camera_pos = world_to_camera.Transform(world_pos)
            
            # Get viewport dimensions
            if hasattr(viewport_api, 'get_texture'):
                texture = viewport_api.get_texture()
                if texture:
                    width = texture.resolution[0]
                    height = texture.resolution[1]
                else:
                    return None, None, False
            else:
                # Fallback: try to get from viewport window
                from omni.kit.viewport.utility import get_active_viewport_window
                viewport_window = get_active_viewport_window()
                if viewport_window:
                    width = viewport_window.content_width if hasattr(viewport_window, 'content_width') else 1920
                    height = viewport_window.content_height if hasattr(viewport_window, 'content_height') else 1080
                else:
                    return None, None, False
            
            # Project to NDC (Normalized Device Coordinates) using camera
            camera_attr = camera_prim.GetAttribute("projection")
            projection = camera_attr.Get() if camera_attr else "perspective"
            
            # Simple perspective projection (assuming perspective camera)
            if camera_pos[2] >= 0:  # Behind camera
                return None, None, False
            
            # Get camera attributes
            focal_length = camera.GetFocalLengthAttr().Get()
            horizontal_aperture = camera.GetHorizontalApertureAttr().Get()
            vertical_aperture = camera.GetVerticalApertureAttr().Get()
            
            # Calculate NDC coordinates
            aspect = width / height if height > 0 else 1.0
            ndc_x = -camera_pos[0] / (camera_pos[2] * horizontal_aperture / focal_length * 0.5)
            ndc_y = -camera_pos[1] / (camera_pos[2] * vertical_aperture / focal_length * 0.5 / aspect)
            
            # Check if in view frustum
            in_view = abs(ndc_x) <= 1.0 and abs(ndc_y) <= 1.0
            
            # Convert NDC to screen pixels
            screen_x = (ndc_x + 1.0) * 0.5 * width
            screen_y = (1.0 - ndc_y) * 0.5 * height  # Flip Y axis
            
            return int(screen_x), int(screen_y), in_view
            
        except Exception as e:
            # Projection failed
            return None, None, False
    
    def _setup_waypoint_hover_detection(self):
        """Set up hover detection using screen-space proximity checking"""
        try:
            # Subscribe to update events to project waypoint positions each frame
            update_count = [0]  # Use list to allow modification in closure
            def on_update(e):
                """Update waypoint screen positions each frame"""
                try:
                    from omni.kit.viewport.utility import get_active_viewport_window, get_active_viewport
                    
                    update_count[0] += 1
                    # Only log every 60 frames (about once per second at 60fps) to avoid spam
                    debug_update = (update_count[0] % 60 == 0)
                    
                    viewport_window = get_active_viewport_window()
                    if not viewport_window:
                        if debug_update:
                            print("[Waypoint Extension] Hover update: No viewport window", flush=True)
                        return
                    
                    viewport = get_active_viewport()
                    if not viewport:
                        if debug_update:
                            print("[Waypoint Extension] Hover update: No active viewport", flush=True)
                        return
                    
                    viewport_api = viewport.viewport_api if hasattr(viewport, 'viewport_api') else viewport
                    
                    # Project all waypoint positions to screen space
                    stage = self._usd_context.get_stage()
                    if not stage:
                        if debug_update:
                            print("[Waypoint Extension] Hover update: No stage", flush=True)
                        return
                    
                    self._waypoint_screen_positions.clear()
                    projected_count = 0
                    
                    for waypoint_path in self._waypoint_paths:
                        waypoint_data = self._waypoint_data.get(waypoint_path, {})
                        icon_position = waypoint_data.get('icon_position')
                        
                        if icon_position:
                            world_pos = Gf.Vec3d(*icon_position)
                            screen_x, screen_y, in_view = self._world_to_screen(world_pos, viewport_api)
                            
                            if screen_x is not None and screen_y is not None:
                                self._waypoint_screen_positions[waypoint_path] = (screen_x, screen_y, in_view)
                                projected_count += 1
                                if debug_update:
                                    print(f"[Waypoint Extension] Projected {waypoint_path}: ({screen_x}, {screen_y}), in_view={in_view}", flush=True)
                    
                    if debug_update and len(self._waypoint_paths) > 0:
                        print(f"[Waypoint Extension] Hover update: {projected_count}/{len(self._waypoint_paths)} waypoints projected", flush=True)
                        sys.stdout.flush()
                
                except Exception as e:
                    # Log errors occasionally
                    if update_count[0] % 300 == 0:
                        print(f"[Waypoint Extension] Hover update error: {e}", flush=True)
                        import traceback
                        traceback.print_exc()
                        sys.stdout.flush()
            
            # Subscribe to update events (called each frame) - just for projecting waypoints
            import carb.eventdispatcher
            ed = carb.eventdispatcher.get_eventdispatcher()
            self._update_subscription = ed.observe_event(
                observer_name="younite.waypoint_customization_extension/update",
                event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
                on_event=on_update,
                order=0,
            )
            
            # Subscribe to mouse move events as per documentation
            mouse_event_count = [0]
            def on_mouse(ev: carb.input.MouseEvent) -> bool:
                """Handle mouse move events to detect hover - following documentation pattern"""
                try:
                    mouse_event_count[0] += 1
                    debug_mouse = (mouse_event_count[0] % 30 == 0)  # Log every 30 events
                    
                    # Only process MOVE events
                    if ev.type.name != "MOVE":
                        return False  # Don't consume event
                    
                    # Get mouse coordinates from event (as per documentation)
                    mouse_x = None
                    mouse_y = None
                    
                    try:
                        # Documentation shows: mx, my = ev.pixel_coords.x, ev.pixel_coords.y
                        if hasattr(ev, 'pixel_coords'):
                            if hasattr(ev.pixel_coords, 'x'):
                                mouse_x = ev.pixel_coords.x
                            elif hasattr(ev.pixel_coords, '__getitem__'):
                                mouse_x = ev.pixel_coords[0]
                            
                            if hasattr(ev.pixel_coords, 'y'):
                                mouse_y = ev.pixel_coords.y
                            elif hasattr(ev.pixel_coords, '__getitem__') and len(ev.pixel_coords) > 1:
                                mouse_y = ev.pixel_coords[1]
                    except Exception as e:
                        if debug_mouse:
                            print(f"[Waypoint Extension] Error extracting pixel_coords: {e}", flush=True)
                            if hasattr(ev, '__dict__'):
                                print(f"[Waypoint Extension] Event attrs: {list(ev.__dict__.keys())}", flush=True)
                        return False
                    
                    if mouse_x is None or mouse_y is None:
                        if debug_mouse:
                            print(f"[Waypoint Extension] Could not get mouse coordinates from event", flush=True)
                            print(f"[Waypoint Extension] Event type: {type(ev)}, type.name: {ev.type.name if hasattr(ev.type, 'name') else 'N/A'}", flush=True)
                        return False
                    
                    if debug_mouse:
                        print(f"[Waypoint Extension] Mouse at: ({mouse_x}, {mouse_y}), checking {len(self._waypoint_screen_positions)} waypoints", flush=True)
                        sys.stdout.flush()
                    
                    # Check if mouse is near any waypoint icon (24px hit box) - as per documentation
                    hit_radius = 24  # pixels (12px in each direction = 24px box)
                    hovered_path = None
                    min_distance = float('inf')
                    
                    for waypoint_path, (screen_x, screen_y, in_view) in self._waypoint_screen_positions.items():
                        if in_view:
                            # Documentation uses: abs(mx-sx) < 12 and abs(my-sy) < 12
                            # We'll use distance for more precise detection
                            distance = ((mouse_x - screen_x) ** 2 + (mouse_y - screen_y) ** 2) ** 0.5
                            if debug_mouse:
                                print(f"[Waypoint Extension]   {waypoint_path}: screen=({screen_x}, {screen_y}), distance={distance:.1f}px", flush=True)
                            if distance < hit_radius and distance < min_distance:
                                hovered_path = waypoint_path
                                min_distance = distance
                    
                    # Update hover state
                    if hovered_path and hovered_path != self._last_hovered_waypoint:
                        print(f"[Waypoint Extension] 🖱️ MOUSE HOVER DETECTED: {hovered_path} (distance: {min_distance:.1f}px)", flush=True)
                        sys.stdout.flush()
                        self._on_waypoint_hover(hovered_path)
                    elif not hovered_path and self._last_hovered_waypoint:
                        self._on_waypoint_hover_exit()
                    
                    return False  # Don't consume the event - allow other handlers to process it
                
                except Exception as e:
                    # Log errors occasionally
                    if mouse_event_count[0] % 100 == 0:
                        print(f"[Waypoint Extension] Mouse event error: {e}", flush=True)
                        import traceback
                        traceback.print_exc()
                        sys.stdout.flush()
                    return False
            
            # Subscribe to mouse input events as per documentation
            # The API expects: (eventFn: Callable[[carb.input.InputEvent], bool], eventTypes: int, ...)
            input_interface = carb.input.acquire_input_interface()
            if input_interface:
                # Create wrapper that accepts InputEvent and checks if it's a MouseEvent
                input_event_count = [0]
                def on_input_event(ev: carb.input.InputEvent) -> bool:
                    """Wrapper to handle InputEvent and check if it's a MouseEvent"""
                    input_event_count[0] += 1
                    if input_event_count[0] % 100 == 0:  # Log every 100 input events
                        print(f"[Waypoint Extension] Input event received: {type(ev).__name__}, total: {input_event_count[0]}", flush=True)
                        sys.stdout.flush()
                    
                    if isinstance(ev, carb.input.MouseEvent):
                        return on_mouse(ev)
                    return False  # Don't consume the event
                
                # Use mouse event type constant - try to find the correct constant
                # The eventTypes is a bitmask, default is 0xFFFFFFFF (all events)
                # For mouse events specifically, we might need to use carb.input.InputEventType constants
                try:
                    # Try to use specific mouse event type constant if available
                    try:
                        mouse_event_type = carb.input.InputEventType.MOUSE_MOVE
                        print(f"[Waypoint Extension] Using specific mouse event type: {mouse_event_type}", flush=True)
                        sys.stdout.flush()
                        self._mouse_input_sub = input_interface.subscribe_to_input_events(
                            on_input_event,
                            mouse_event_type
                        )
                    except (AttributeError, NameError):
                        # Fallback: subscribe to all events and filter in the callback
                        # 0xFFFFFFFF is the default (all event types)
                        print("[Waypoint Extension] Mouse event type constant not found, subscribing to all events", flush=True)
                        sys.stdout.flush()
                        self._mouse_input_sub = input_interface.subscribe_to_input_events(
                            on_input_event,
                            0xFFFFFFFF  # All input events
                        )
                    
                    print(f"[Waypoint Extension] ✅ Mouse input subscription created successfully: {self._mouse_input_sub}", flush=True)
                    print(f"[Waypoint Extension] Subscription active - waiting for mouse events...", flush=True)
                    sys.stdout.flush()
                except Exception as sub_error:
                    print(f"[Waypoint Extension] ❌ Failed to create subscription: {sub_error}", flush=True)
                    import traceback
                    traceback.print_exc()
                    sys.stdout.flush()
                    self._mouse_input_sub = None
            else:
                print("[Waypoint Extension] ⚠️ Could not acquire input interface", flush=True)
            
            print("[Waypoint Extension] ✅ Hover detection setup: using screen-space proximity (24px radius)", flush=True)
            print(f"[Waypoint Extension] Tracking {len(self._waypoint_paths)} waypoints for hover", flush=True)
            print("[Waypoint Extension] Mouse events subscribed via carb.input", flush=True)
            sys.stdout.flush()
            
        except Exception as e:
            print(f"[Waypoint Extension] Could not set up waypoint hover detection: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
    
    def _on_selection_changed_for_hover(self, event):
        """Handle selection changes to detect waypoint hover/selection"""
        try:
            if event.type != int(omni.usd.StageEventType.SELECTION_CHANGED):
                return
            
            # Get selected prims
            selection = self._usd_context.get_selection()
            if not selection:
                return
            
            selected_paths = selection.get_selected_prim_paths()
            
            # Check if any selected path is a waypoint
            for selected_path in selected_paths:
                if selected_path.startswith("/Viewport_Waypoints/"):
                    # Waypoint is selected/hovered - log it
                    self._on_waypoint_hover(selected_path)
                    return
            
            # No waypoint selected - clear hover
            if self._last_hovered_waypoint:
                self._on_waypoint_hover_exit()
                
        except Exception as e:
            # Don't spam errors
            pass

    def _on_stage_event(self, event):
        """Handle stage events to detect waypoint changes"""
        print(f"[Waypoint Extension] Stage event received: type={event.type}, OPENED={int(omni.usd.StageEventType.OPENED)}", flush=True)
        sys.stdout.flush()
        if event.type == int(omni.usd.StageEventType.OPENED):
            print("[Waypoint Extension] Stage opened event detected, loading waypoints...", flush=True)
            sys.stdout.flush()
            asyncio.ensure_future(self._load_waypoints())
    
    def _attach_icon_click(self, waypoint_prim):
        """Create and store ViewportWaypoint instance for navigation
        
        Note: We use monkey-patch of ViewportWaypoint.recall instead of icon_click
        because the waypoint system creates its own instances that we can't replace.
        """
        try:
            waypoint_path = str(waypoint_prim.GetPath())
            
            # Create ViewportWaypoint instance for later navigation
            viewport_waypoint = ViewportWaypoint.create_from_prim(waypoint_prim)
            
            # Store the waypoint instance for navigation
            self._viewport_waypoints[waypoint_path] = viewport_waypoint
            
            print(f"[Waypoint Extension] ✅ Stored ViewportWaypoint instance for: {waypoint_path}", flush=True)
            sys.stdout.flush()
            
            return viewport_waypoint
            
        except Exception as e:
            print(f"[Waypoint Extension] ERROR creating ViewportWaypoint: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            return None

    async def _load_waypoints(self):
        """Load and process waypoints from the stage"""
        print("[Waypoint Extension] _load_waypoints() called", flush=True)
        sys.stdout.flush()
        try:
            stage = self._usd_context.get_stage()
            if not stage:
                print("[Waypoint Extension] WARNING: No stage available", flush=True)
                sys.stdout.flush()
                return
            
            print(f"[Waypoint Extension] Stage obtained: {stage}", flush=True)
            sys.stdout.flush()
            
            # Find waypoint prims
            waypoints_prim = stage.GetPrimAtPath("/Viewport_Waypoints")
            print(f"[Waypoint Extension] Looking for /Viewport_Waypoints: found={waypoints_prim is not None}, valid={waypoints_prim.IsValid() if waypoints_prim else False}", flush=True)
            sys.stdout.flush()
            
            if not waypoints_prim or not waypoints_prim.IsValid():
                print("[Waypoint Extension] WARNING: No Viewport_Waypoints found in stage", flush=True)
                sys.stdout.flush()
                # Try to list root prims for debugging
                root_prim = stage.GetPrimAtPath("/")
                if root_prim and root_prim.IsValid():
                    print(f"[Waypoint Extension] Root prim children: {[child.GetName() for child in root_prim.GetChildren()]}", flush=True)
                    sys.stdout.flush()
                return
            
            # Process each waypoint
            children = list(waypoints_prim.GetChildren())
            print(f"[Waypoint Extension] Found {len(children)} waypoint children", flush=True)
            sys.stdout.flush()
            
            # Store waypoint paths for click detection
            self._waypoint_paths = []
            
            for child in children:
                if child.IsValid():
                    waypoint_path = child.GetPath()
                    waypoint_name = child.GetName()
                    print(f"[Waypoint Extension] Processing waypoint: {waypoint_name} at {waypoint_path}", flush=True)
                    sys.stdout.flush()
                    
                    # Process waypoint data
                    self._process_waypoint(child)
                    self._waypoint_paths.append(waypoint_path)
                    
                    # Create ViewportWaypoint instance with custom icon_click handler
                    # This replaces the monkey-patch approach
                    self._attach_icon_click(child)
                else:
                    print(f"[Waypoint Extension] WARNING: Invalid waypoint child: {child}", flush=True)
                    sys.stdout.flush()
            
            print(f"[Waypoint Extension] ✅ Loaded {len(self._waypoint_data)} waypoints", flush=True)
            sys.stdout.flush()
            
            # Refresh waypoint browser if it exists
            if self._waypoint_browser_window:
                asyncio.ensure_future(self._populate_waypoint_browser())
                    
        except Exception as e:
            print(f"[Waypoint Extension] ERROR loading waypoints: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()

    def _process_waypoint(self, waypoint_prim):
        """
        Process a waypoint and extract available data
        
        Available waypoint properties (from ViewportWaypoint class):
        - comment: str - The comment/description
        - create_time: str - When it was created
        - created_by: str - Who created it
        - thumbnail: str | None - Path to thumbnail image
        - thumbnail_data: Tuple[bytes, int, int] | None - Thumbnail data (bytes, width, height)
        - camera_prim: Prim | None - Associated camera prim
        - frame: float - Frame number
        - name: str - Waypoint name
        - path: str - Full USD path
        - info: str - Concatenated info from all settings
        """
        try:
            waypoint_name = waypoint_prim.GetName()
            waypoint_path = str(waypoint_prim.GetPath())
            
            # Extract available attributes
            waypoint_data = {
                'name': waypoint_name,
                'path': waypoint_path,
            }
            
            # Get comment
            comment_attr = waypoint_prim.GetAttribute("comment")
            if comment_attr and comment_attr.HasValue():
                waypoint_data['comment'] = comment_attr.Get()
            
            # Get creation info
            created_attr = waypoint_prim.GetAttribute("created")
            if created_attr and created_attr.HasValue():
                waypoint_data['created'] = created_attr.Get()
            
            created_by_attr = waypoint_prim.GetAttribute("created_by")
            if created_by_attr and created_by_attr.HasValue():
                waypoint_data['created_by'] = created_by_attr.Get()
            
            # Get frame
            frame_attr = waypoint_prim.GetAttribute("frame")
            if frame_attr and frame_attr.HasValue():
                waypoint_data['frame'] = frame_attr.Get()
            
            # Get icon position (for 3D display)
            icon_pos_attr = waypoint_prim.GetAttribute("icon_position")
            if icon_pos_attr and icon_pos_attr.HasValue():
                waypoint_data['icon_position'] = icon_pos_attr.Get()
            
            # Get thumbnail path (if stored)
            # Note: Thumbnails might be in omni:baked_preview attribute
            baked_preview_attr = waypoint_prim.GetAttribute("omni:baked_preview")
            if baked_preview_attr and baked_preview_attr.HasValue():
                waypoint_data['thumbnail_data'] = baked_preview_attr.Get()
            
            # Get camera path
            camera_path_attr = waypoint_prim.GetAttribute("camera:path")
            if camera_path_attr and camera_path_attr.HasValue():
                waypoint_data['camera_path'] = camera_path_attr.Get()
            
            # Store waypoint data
            self._waypoint_data[waypoint_path] = waypoint_data
            
            print(f"[Waypoint Extension] ✅ Processed waypoint '{waypoint_name}':", flush=True)
            print(f"  - Path: {waypoint_path}", flush=True)
            print(f"  - Comment: {waypoint_data.get('comment', 'N/A')}", flush=True)
            print(f"  - Created by: {waypoint_data.get('created_by', 'N/A')}", flush=True)
            print(f"  - Created: {waypoint_data.get('created', 'N/A')}", flush=True)
            print(f"  - Icon position: {waypoint_data.get('icon_position', 'N/A')}", flush=True)
            print(f"  - Has thumbnail: {'Yes' if waypoint_data.get('thumbnail_data') else 'No'}", flush=True)
            sys.stdout.flush()
            
            # Example: Create custom tooltip/hover display
            self._create_waypoint_tooltip(waypoint_path, waypoint_data)
            
            # Example: Add custom UI button
            self._create_custom_button(waypoint_path, waypoint_data)
            
        except Exception as e:
            print(f"[Waypoint Extension] ERROR processing waypoint: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()

    def _create_waypoint_tooltip(self, waypoint_path: str, waypoint_data: dict):
        """
        Create a tooltip that shows when hovering over a waypoint
        
        This can be implemented using:
        1. Viewport overlay UI
        2. Custom delegate for WaypointCard
        3. USD prim metadata display
        """
        # Build tooltip text
        tooltip_parts = []
        
        if waypoint_data.get('comment'):
            tooltip_parts.append(f"📍 {waypoint_data['comment']}")
        
        if waypoint_data.get('created_by'):
            tooltip_parts.append(f"Created by: {waypoint_data['created_by']}")
        
        if waypoint_data.get('created'):
            tooltip_parts.append(f"Date: {waypoint_data['created']}")
        
        tooltip_text = "\n".join(tooltip_parts)
        
        # Store tooltip for later use
        self._waypoint_data[waypoint_path]['tooltip'] = tooltip_text
        
        print(f"[Waypoint Extension] Created tooltip for {waypoint_path}: {tooltip_text}", flush=True)
        sys.stdout.flush()

    def _create_custom_button(self, waypoint_path: str, waypoint_data: dict):
        """
        Create a custom button/UI element for the waypoint
        
        This could be:
        1. A button in a custom waypoint browser
        2. An overlay button in the viewport
        3. A custom WaypointCard with embedded controls
        """
        # Store button configuration
        button_config = {
            'label': f"Go to {waypoint_data['name']}",
            'action': lambda: self._navigate_to_waypoint(waypoint_path),
            'icon': waypoint_data.get('thumbnail_data'),  # Use thumbnail as icon if available
        }
        
        self._waypoint_data[waypoint_path]['button'] = button_config
        
        print(f"[Waypoint Extension] Created button config for {waypoint_path}", flush=True)
        sys.stdout.flush()

    def _navigate_to_waypoint(self, waypoint_path: str):
        """Navigate camera to the waypoint"""
        try:
            print(f"[Waypoint Extension] _navigate_to_waypoint called for: {waypoint_path}", flush=True)
            sys.stdout.flush()
            
            # Create ViewportWaypoint from prim
            stage = self._usd_context.get_stage()
            waypoint_prim = stage.GetPrimAtPath(waypoint_path)
            
            if waypoint_prim and waypoint_prim.IsValid():
                # Create waypoint instance and recall it
                viewport_waypoint = ViewportWaypoint.create_from_prim(waypoint_prim)
                if viewport_waypoint:
                    print(f"[Waypoint Extension] Calling recall on waypoint: {waypoint_path}", flush=True)
                    sys.stdout.flush()
                    viewport_waypoint.recall(without_camera=False)
                    print(f"[Waypoint Extension] Navigated to waypoint: {waypoint_path}", flush=True)
                else:
                    print(f"[Waypoint Extension] WARNING: Could not create ViewportWaypoint from prim", flush=True)
                sys.stdout.flush()
            else:
                print(f"[Waypoint Extension] WARNING: Waypoint prim not found or invalid: {waypoint_path}", flush=True)
                sys.stdout.flush()
                    
        except Exception as e:
            print(f"[Waypoint Extension] ERROR navigating to waypoint: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
    
    def _intercept_waypoint_click(self, waypoint_path: str):
        """Intercept waypoint click to show popup instead of immediate navigation"""
        try:
            print(f"[Waypoint Extension] Intercepting click for waypoint: {waypoint_path}", flush=True)
            sys.stdout.flush()
            
            # Check if this is a waypoint we know about
            if waypoint_path in self._waypoint_data:
                # Show popup instead of navigating immediately
                self._show_waypoint_popup(waypoint_path)
                return True  # Indicate we handled it
            
            return False  # Let default behavior happen
            
        except Exception as e:
            print(f"[Waypoint Extension] ERROR intercepting waypoint click: {e}", flush=True)
            sys.stdout.flush()
            return False

    def get_waypoint_info(self, waypoint_path: str) -> dict:
        """Get all available information about a waypoint"""
        return self._waypoint_data.get(waypoint_path, {})
    
    def _create_tooltip_overlay(self):
        """Create a floating tooltip window that appears on hover"""
        try:
            # Create a small floating window for tooltips
            self._tooltip_window = ui.Window(
                "Waypoint Tooltip",
                width=300,
                height=150,
                visible=False,  # Hidden by default, shown on hover
            )
            
            with self._tooltip_window.frame:
                with ui.VStack(spacing=5):
                    self._tooltip_label = ui.Label(
                        "",
                        word_wrap=True,
                        style={"margin": 5},
                    )
            
            print("[Waypoint Extension] Tooltip overlay created", flush=True)
            sys.stdout.flush()
        except Exception as e:
            print(f"[Waypoint Extension] ERROR creating tooltip overlay: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
    
    def _create_waypoint_browser(self):
        """Create a window that displays all waypoints with thumbnails and buttons"""
        try:
            # Check if browser window should be visible by default
            settings = carb.settings.get_settings()
            show_browser = settings.get("/exts/younite.waypoint_customization_extension/show_browser_window")
            if show_browser is None:
                show_browser = False  # Default to hidden
            
            self._waypoint_browser_window = ui.Window(
                "Waypoints",
                width=400,
                height=600,
                visible=show_browser,  # Use setting to control visibility
            )
            
            with self._waypoint_browser_window.frame:
                with ui.VStack(spacing=5, style={"margin": 5}):
                    ui.Label("Waypoints", style={"font_size": 20})
                    
                    # Create a scrollable area for waypoint cards
                    with ui.ScrollingFrame():
                        with ui.VStack(spacing=10, style={"margin": 5}):
                            # Waypoint cards will be added here dynamically
                            self._waypoint_cards_container = ui.VStack(spacing=10)
            
            print("[Waypoint Extension] Waypoint browser window created", flush=True)
            sys.stdout.flush()
            
            # Refresh browser when waypoints are loaded
            asyncio.ensure_future(self._populate_waypoint_browser())
            
        except Exception as e:
            print(f"[Waypoint Extension] ERROR creating waypoint browser: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
    
    async def _populate_waypoint_browser(self):
        """Populate the browser with waypoint cards"""
        # Wait for waypoints to be loaded and UI to be ready
        await asyncio.sleep(1.0)
        
        if not self._waypoint_browser_window:
            print("[Waypoint Extension] WARNING: Browser window not available for population", flush=True)
            sys.stdout.flush()
            return
        
        try:
            print(f"[Waypoint Extension] Populating waypoint browser with {len(self._waypoint_data)} waypoints...", flush=True)
            sys.stdout.flush()
            
            if not self._waypoint_data:
                print("[Waypoint Extension] WARNING: No waypoint data available to display", flush=True)
                sys.stdout.flush()
                return
            
            # Create a card for each waypoint
            card_count = 0
            for waypoint_path, waypoint_data in self._waypoint_data.items():
                print(f"[Waypoint Extension] Creating card for: {waypoint_path}", flush=True)
                sys.stdout.flush()
                self._create_waypoint_card(waypoint_path, waypoint_data)
                card_count += 1
            
            print(f"[Waypoint Extension] ✅ Browser populated with {card_count} waypoint cards", flush=True)
            sys.stdout.flush()
        except Exception as e:
            print(f"[Waypoint Extension] ERROR populating browser: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
    
    def _create_waypoint_card(self, waypoint_path: str, waypoint_data: dict):
        """Create a card UI element for a single waypoint"""
        try:
            if not hasattr(self, '_waypoint_cards_container'):
                return
            
            with self._waypoint_cards_container:
                with ui.Frame(style={"background_color": 0xFF222222, "padding": 10}):
                    with ui.VStack(spacing=5):
                        # Show comment instead of prim name
                        comment = waypoint_data.get('comment', '')
                        if comment:
                            ui.Label(
                                comment,
                                word_wrap=True,
                                style={"font_size": 16, "color": 0xFFFFFFFF}
                            )
                        else:
                            # Fallback if no comment
                            ui.Label(
                                waypoint_data.get('name', 'Unknown'),
                                style={"font_size": 16, "color": 0xFFFFFFFF}
                            )
                        
                        # Thumbnail if available
                        thumbnail_data = waypoint_data.get('thumbnail_data')
                        if thumbnail_data:
                            thumbnail_image = self._decode_thumbnail(thumbnail_data)
                            if thumbnail_image:
                                with ui.HStack():
                                    ui.Image(
                                        thumbnail_image,
                                        width=150,
                                        height=100,
                                        fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                    )
                        
                        # Metadata
                        with ui.VStack(spacing=2):
                            if waypoint_data.get('created_by'):
                                ui.Label(
                                    f"Created by: {waypoint_data['created_by']}",
                                    style={"font_size": 11, "color": 0xFFAAAAAA}
                                )
                            if waypoint_data.get('created'):
                                ui.Label(
                                    f"Date: {waypoint_data['created']}",
                                    style={"font_size": 11, "color": 0xFFAAAAAA}
                                )
                        
                        # Navigation button
                        def make_navigate_fn(path):
                            def navigate():
                                print(f"[Waypoint Extension] Move There clicked for: {path}", flush=True)
                                sys.stdout.flush()
                                # Show tooltip briefly
                                self.show_tooltip(path, 200, 200)
                                # Navigate to waypoint
                                self._navigate_to_waypoint(path)
                            return navigate
                        
                        ui.Button(
                            "Move There",
                            clicked_fn=make_navigate_fn(waypoint_path),
                            style={"margin": 5}
                        )
            
        except Exception as e:
            print(f"[Waypoint Extension] ERROR creating waypoint card: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
    
    def _get_thumbnail_provider(self, waypoint_path: str, thumbnail_data):
        """Get or create an in-memory image provider for thumbnail data
        
        Returns a ui.ByteImageProvider for use with ui.ImageWithProvider
        This avoids temp file creation and cleanup
        """
        try:
            if not thumbnail_data:
                return None
            
            # Check if we already have a provider for this waypoint
            if waypoint_path in self._thumbnail_providers:
                return self._thumbnail_providers[waypoint_path]
            
            # Decode thumbnail data to bytes
            image_bytes = None
            
            if isinstance(thumbnail_data, (tuple, list)):
                if len(thumbnail_data) > 0:
                    image_bytes = thumbnail_data[0]
                    if isinstance(image_bytes, str):
                        try:
                            image_bytes = base64.b64decode(image_bytes)
                        except:
                            image_bytes = image_bytes.encode('latin-1')
            elif isinstance(thumbnail_data, bytes):
                image_bytes = thumbnail_data
            elif isinstance(thumbnail_data, str):
                try:
                    image_bytes = base64.b64decode(thumbnail_data)
                except Exception:
                    image_bytes = thumbnail_data.encode('latin-1')
            else:
                return None
            
            if not image_bytes or len(image_bytes) < 100:
                return None
            
            # Validate image format
            if not (image_bytes[:2] == b'\xFF\xD8' or image_bytes[:4] == b'\x89PNG'):
                return None
            
            # Create in-memory image provider
            try:
                provider = ui.ByteImageProvider(image_bytes)
                self._thumbnail_providers[waypoint_path] = provider
                return provider
            except Exception as e:
                print(f"[Waypoint Extension] ERROR creating thumbnail provider: {e}", flush=True)
                sys.stdout.flush()
                return None
            
        except Exception as e:
            print(f"[Waypoint Extension] ERROR getting thumbnail provider: {e}", flush=True)
            sys.stdout.flush()
            return None
    
    def _decode_thumbnail(self, thumbnail_data):
        """Decode thumbnail data into a temporary file (fallback method)
        
        This is kept as a fallback if in-memory providers don't work.
        Prefer using _get_thumbnail_provider() instead.
        """
        try:
            if not thumbnail_data:
                return None
            
            import tempfile
            import os
            
            image_bytes = None
            
            # Check the type of thumbnail_data
            if isinstance(thumbnail_data, (tuple, list)):
                if len(thumbnail_data) > 0:
                    image_bytes = thumbnail_data[0]
                    if isinstance(image_bytes, str):
                        try:
                            image_bytes = base64.b64decode(image_bytes)
                        except:
                            image_bytes = image_bytes.encode('latin-1')
            elif isinstance(thumbnail_data, bytes):
                image_bytes = thumbnail_data
            elif isinstance(thumbnail_data, str):
                try:
                    image_bytes = base64.b64decode(thumbnail_data)
                except Exception:
                    image_bytes = thumbnail_data.encode('latin-1')
            else:
                return None
            
            if not image_bytes or len(image_bytes) < 100:
                return None
            
            # Determine file extension based on magic bytes
            file_ext = None
            if image_bytes[:2] == b'\xFF\xD8':
                file_ext = '.jpg'
            elif image_bytes[:4] == b'\x89PNG':
                file_ext = '.png'
            else:
                return None
            
            # Write to temporary file (fallback only)
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                tmp_file.write(image_bytes)
                tmp_path = tmp_file.name
            
            abs_path = os.path.abspath(tmp_path)
            if not os.path.exists(abs_path):
                return None
            
            return abs_path
            
        except Exception as e:
            print(f"[Waypoint Extension] ERROR decoding thumbnail: {e}", flush=True)
            sys.stdout.flush()
            return None
    
    def show_tooltip(self, waypoint_path: str, x: int = 0, y: int = 0):
        """Show tooltip for a waypoint at specified screen coordinates"""
        try:
            waypoint_data = self._waypoint_data.get(waypoint_path)
            if not waypoint_data:
                return
            
            tooltip_text = waypoint_data.get('tooltip', '')
            if not tooltip_text:
                return
            
            # Create tooltip window if it doesn't exist
            if not self._tooltip_window:
                self._create_tooltip_overlay()
            
            if self._tooltip_label:
                self._tooltip_label.text = tooltip_text
            
            # Position and show the tooltip
            if x > 0 or y > 0:
                self._tooltip_window.set_position(x + 10, y + 10)
            
            self._tooltip_window.visible = True
            self._current_hovered_waypoint = waypoint_path
            
        except Exception as e:
            print(f"[Waypoint Extension] ERROR showing tooltip: {e}", flush=True)
            sys.stdout.flush()
    
    def hide_tooltip(self):
        """Hide the tooltip"""
        try:
            if self._tooltip_window:
                self._tooltip_window.visible = False
            self._current_hovered_waypoint = None
        except Exception as e:
            print(f"[Waypoint Extension] ERROR hiding tooltip: {e}", flush=True)
            sys.stdout.flush()
    
    def show_browser_window(self):
        """Show the waypoint browser window"""
        try:
            if not self._waypoint_browser_window:
                self._create_waypoint_browser()
            self._waypoint_browser_window.visible = True
            print("[Waypoint Extension] Waypoint browser window shown", flush=True)
            sys.stdout.flush()
        except Exception as e:
            print(f"[Waypoint Extension] ERROR showing browser: {e}", flush=True)
            sys.stdout.flush()
    
    def hide_browser_window(self):
        """Hide the waypoint browser window"""
        try:
            if self._waypoint_browser_window:
                self._waypoint_browser_window.visible = False
                print("[Waypoint Extension] Waypoint browser window hidden", flush=True)
                sys.stdout.flush()
        except Exception as e:
            print(f"[Waypoint Extension] ERROR hiding browser: {e}", flush=True)
            sys.stdout.flush()
    
    def _show_waypoint_popup(self, waypoint_path: str):
        """Show a compact, borderless popup dialog with waypoint information and action buttons"""
        try:
            waypoint_data = self._waypoint_data.get(waypoint_path)
            if not waypoint_data:
                # Create minimal data from path if not available
                waypoint_name = waypoint_path.split("/")[-1] if "/" in waypoint_path else waypoint_path
                waypoint_data = {
                    'name': waypoint_name,
                    'path': waypoint_path,
                }
                print(f"[Waypoint Extension] WARNING: No data for waypoint {waypoint_path}, using minimal data", flush=True)
                sys.stdout.flush()
            
            # Close existing popup if any
            self._hide_waypoint_popup()
            
            # Get comment for window title (empty string for borderless)
            comment = waypoint_data.get('comment', '')
            window_title = comment if comment else waypoint_data.get('name', 'Waypoint')
            
            # Create borderless, compact popup window
            self._waypoint_popup = ui.Window(
                "",  # No title bar text (borderless)
                width=320,
                height=220,
                flags=ui.WINDOW_FLAGS_NO_TITLE_BAR | ui.WINDOW_FLAGS_NO_RESIZE | ui.WINDOW_FLAGS_NO_SCROLLBAR,
                visible=True,
            )
            
            # Center the window
            try:
                if hasattr(self._waypoint_popup, 'setPosition'):
                    self._waypoint_popup.setPosition(400, 300)
            except Exception as pos_error:
                print(f"[Waypoint Extension] Could not set window position: {pos_error}", flush=True)
                sys.stdout.flush()
            
            # Create UI content
            frame = self._waypoint_popup.frame
            if not frame:
                print(f"[Waypoint Extension] ERROR: Window frame is None!", flush=True)
                sys.stdout.flush()
                return
            
            with frame:
                # Background frame with rounded corners
                with ui.Frame(style={"background_color": 0xE0222222, "border_radius": 8, "padding": 12}):
                    with ui.VStack(spacing=8):
                        # Comment as main heading
                        if comment:
                            ui.Label(
                                comment,
                                word_wrap=True,
                                style={"font_size": 16, "color": 0xFFFFFFFF, "margin_bottom": 4}
                            )
                        else:
                            # Fallback if no comment
                            waypoint_name = waypoint_data.get('name', 'Waypoint')
                            ui.Label(
                                waypoint_name,
                                style={"font_size": 16, "color": 0xFFFFFFFF, "margin_bottom": 4}
                            )
                        
                        # Thumbnail if available
                        thumbnail_data = waypoint_data.get('thumbnail_data')
                        if thumbnail_data:
                            # Try in-memory provider first, fallback to temp file
                            thumbnail_provider = self._get_thumbnail_provider(waypoint_path, thumbnail_data)
                            if thumbnail_provider:
                                try:
                                    # Try ImageWithProvider if available
                                    if hasattr(ui, 'ImageWithProvider'):
                                        ui.ImageWithProvider(thumbnail_provider, width=296, height=120, fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT)
                                    else:
                                        # Fallback to temp file
                                        thumbnail_image = self._decode_thumbnail(thumbnail_data)
                                        if thumbnail_image:
                                            ui.Image(thumbnail_image, width=296, height=120, fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT)
                                except Exception as img_error:
                                    # Fallback to file-based image if provider fails
                                    thumbnail_image = self._decode_thumbnail(thumbnail_data)
                                    if thumbnail_image:
                                        ui.Image(thumbnail_image, width=296, height=120, fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT)
                                    print(f"[Waypoint Extension] Using file-based thumbnail fallback: {img_error}", flush=True)
                                    sys.stdout.flush()
                            else:
                                # No provider, try temp file
                                thumbnail_image = self._decode_thumbnail(thumbnail_data)
                                if thumbnail_image:
                                    ui.Image(thumbnail_image, width=296, height=120, fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT)
                        
                        # Buttons with explicit sizing and styling
                        with ui.HStack(spacing=8, style={"margin_top": 8}):
                            ui.Spacer()
                            
                            def navigate():
                                print(f"[Waypoint Extension] Go there clicked for: {waypoint_path}", flush=True)
                                sys.stdout.flush()
                                nav_path = waypoint_path
                                asyncio.ensure_future(self._hide_waypoint_popup_delayed())
                                
                                # Execute pending recall if we have one
                                async def navigate_delayed():
                                    await asyncio.sleep(0.05)  # Small delay to ensure UI is ready
                                    if self._pending_recall and self._pending_recall['waypoint_path'] == nav_path:
                                        pending = self._pending_recall
                                        self._pending_recall = None
                                        print(f"[Waypoint Extension] Executing pending recall for: {nav_path}", flush=True)
                                        sys.stdout.flush()
                                        
                                        # Call original recall with stored parameters
                                        if hasattr(ViewportWaypoint, '_original_recall'):
                                            ViewportWaypoint._original_recall(
                                                pending['viewport_waypoint'],
                                                without_camera=pending['without_camera'],
                                                enable_settings=pending['enable_settings'],
                                                disable_settings=pending['disable_settings']
                                            )
                                        else:
                                            # Fallback to our navigate method
                                            self._navigate_to_waypoint(nav_path)
                                    else:
                                        # Fallback to our navigate method
                                        self._navigate_to_waypoint(nav_path)
                                asyncio.ensure_future(navigate_delayed())
                            
                            ui.Button(
                                "Go there",
                                width=120,
                                height=32,
                                clicked_fn=navigate,
                                style={
                                    "background_color": 0xFF3A6EE8,
                                    "border_radius": 6,
                                    "color": 0xFFFFFFFF,
                                    "font_size": 13,
                                }
                            )
                            
                            def cancel():
                                print(f"[Waypoint Extension] Cancel clicked", flush=True)
                                sys.stdout.flush()
                                asyncio.ensure_future(self._hide_waypoint_popup_delayed())
                            
                            ui.Button(
                                "Cancel",
                                width=100,
                                height=32,
                                clicked_fn=cancel,
                                style={
                                    "background_color": 0xFF3A3A3A,
                                    "border_radius": 6,
                                    "color": 0xFFFFFFFF,
                                    "font_size": 13,
                                }
                            )
                            
                            # Keyboard shortcuts: Enter = Go, Esc = Cancel
                            # Note: Keyboard shortcuts need to be handled at window level
                            # For now, buttons are clickable
            
            print(f"[Waypoint Extension] ✅ Popup shown for: {waypoint_path}", flush=True)
            sys.stdout.flush()
            
        except Exception as e:
            print(f"[Waypoint Extension] ERROR showing waypoint popup: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
    
    def _hide_waypoint_popup(self):
        """Hide the waypoint popup dialog (immediate)"""
        try:
            if self._waypoint_popup:
                self._waypoint_popup.visible = False
                self._waypoint_popup.destroy()
                self._waypoint_popup = None
        except Exception as e:
            print(f"[Waypoint Extension] ERROR hiding waypoint popup: {e}", flush=True)
            sys.stdout.flush()
    
    async def _hide_waypoint_popup_delayed(self):
        """Hide the waypoint popup dialog with a delay to avoid destruction during event"""
        try:
            await asyncio.sleep(0.05)  # Small delay to let the event complete
            if self._waypoint_popup:
                self._waypoint_popup.visible = False
                self._waypoint_popup.destroy()
                self._waypoint_popup = None
        except Exception as e:
            print(f"[Waypoint Extension] ERROR hiding waypoint popup (delayed): {e}", flush=True)
            sys.stdout.flush()

    def shutdown(self):
        """Clean up resources"""
        try:
            if self._subscription:
                self._subscription = None
            if self._selection_subscription:
                self._selection_subscription = None
            
            # Clean up ViewportWaypoint instances
            self._viewport_waypoints.clear()
            
            # Clean up thumbnail providers (in-memory, no files to delete)
            self._thumbnail_providers.clear()
            
            # Clean up UI
            if self._tooltip_window:
                self._tooltip_window.destroy()
                self._tooltip_window = None
            
            if self._waypoint_browser_window:
                self._waypoint_browser_window.destroy()
                self._waypoint_browser_window = None
            
            if self._waypoint_popup:
                self._waypoint_popup.destroy()
                self._waypoint_popup = None
            
            self._waypoint_data.clear()
            print("[Waypoint Extension] Manager shutdown complete", flush=True)
            sys.stdout.flush()
        except Exception as e:
            print(f"[Waypoint Extension] ERROR during shutdown: {e}", flush=True)
            sys.stdout.flush()


# Any class derived from `omni.ext.IExt` in top level module (defined in
# `python.modules` of `extension.toml`) will be instantiated when extension
# gets enabled and `on_startup(ext_id)` will be called. Later when extension
# gets disabled on_shutdown() is called.
class Extension(omni.ext.IExt):
    """Waypoint Customization Extension for displaying additional waypoint information"""
    
    def on_startup(self, ext_id):
        """Extension startup"""
        try:
            print("[Waypoint Extension] ========================================", flush=True)
            print("[Waypoint Extension] Waypoint Customization Extension STARTED", flush=True)
            print(f"[Waypoint Extension] ext_id = {ext_id}", flush=True)
            print("[Waypoint Extension] ========================================", flush=True)
            sys.stdout.flush()
            
            self._ext_id = ext_id
            print("[Waypoint Extension] Creating WaypointCustomizationManager...", flush=True)
            sys.stdout.flush()
            
            self._manager = WaypointCustomizationManager()
            print("[Waypoint Extension] WaypointCustomizationManager created successfully", flush=True)
            sys.stdout.flush()
        except Exception as e:
            print(f"[Waypoint Extension] ERROR in on_startup: {e}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            raise
    
    def on_shutdown(self):
        """Extension shutdown"""
        print("[Waypoint Extension] Waypoint Customization Extension shutdown", flush=True)
        sys.stdout.flush()
        if hasattr(self, "_manager"):
            self._manager.shutdown()
            self._manager = None

