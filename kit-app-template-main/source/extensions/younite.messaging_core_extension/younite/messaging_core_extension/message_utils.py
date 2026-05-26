# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# Message normalization utilities for Events 2.0 messaging

import carb
import carb.eventdispatcher
from typing import Any, Dict, Optional, Tuple


def normalize_event_payload(raw_payload: Any) -> Dict[str, Any]:
    """
    Normalize event payload from various formats to a clean dictionary.
    
    Handles formats:
    - { event_type, payload } - wrapped format
    - { event_type, ...other_fields } - direct format
    - Raw dict with internal fields (_Sender, _Event, etc.)
    
    Returns:
        Clean payload dictionary with internal fields filtered out
    """
    if not isinstance(raw_payload, dict):
        return {}
    
    # Extract inner payload if wrapped
    if 'event_type' in raw_payload and 'payload' in raw_payload:
        payload = raw_payload.get('payload', {})
    else:
        payload = raw_payload
    
    # Filter out internal messaging extension fields
    return {k: v for k, v in payload.items() 
            if not str(k).startswith('_') and k != 'event_type'}


def extract_event_from_message(payload: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Extract event_type and clean payload from a message payload.
    
    Args:
        payload: Message payload (dict or other)
        
    Returns:
        Tuple of (event_type, clean_payload) or None if extraction fails
    """
    if not isinstance(payload, dict):
        return None
    
    # Standard format: { event_type, payload }
    if 'event_type' in payload:
        evt_type = payload.get('event_type')
        inner_payload = payload.get('payload', {})
        if isinstance(inner_payload, dict):
            return (evt_type, normalize_event_payload(inner_payload))
        return (evt_type, {})
    
    return None


def dispatch_to_events2(event_type: str, payload: Dict[str, Any]) -> bool:
    """
    Dispatch an event to Events 2.0 system.
    
    Args:
        event_type: Event name
        payload: Event payload dictionary
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import omni.kit.app as kit_app
        ed = carb.eventdispatcher.get_eventdispatcher()
        
        # Register event alias if needed
        try:
            type_id = carb.events.type_from_string(event_type)
            kit_app.register_event_alias(type_id, event_type)
        except Exception:
            pass
        
        # Dispatch event
        ed.dispatch_event(event_type, payload if isinstance(payload, dict) else {})
        return True
    except Exception:
        return False


def register_outbound_events(event_names: list[str]) -> None:
    """
    Register outbound events with omni.kit.livestream.messaging using the singleton instance.
    
    Args:
        event_names: List of event names to register for forwarding to web client
    """
    try:
        import omni.kit.livestream.messaging as messaging_module
        messaging = messaging_module.LivestreamMessaging.instance
        if messaging:
            for event_name in event_names:
                try:
                    messaging.register_event_type_to_send(event_name)
                except Exception:
                    pass
    except Exception:
        pass

