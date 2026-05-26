"""
Messaging core: incoming wrapper-message bridge + outbound registration helpers.
"""

from .extension import MessagingCoreExtension
from .message_utils import register_outbound_events, dispatch_to_events2, normalize_event_payload, extract_event_from_message
from .events_contracts import Events

__all__ = [
    "MessagingCoreExtension",
    "register_outbound_events",
    "dispatch_to_events2",
    "normalize_event_payload",
    "extract_event_from_message",
    "Events",
]

