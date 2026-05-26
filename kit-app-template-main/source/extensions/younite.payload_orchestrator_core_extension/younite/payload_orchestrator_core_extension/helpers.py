"""Convenience wrappers for common orchestrator operations.

Consumer extensions import these instead of manually constructing
PayloadOperation objects and handling RuntimeError.

    from younite.payload_orchestrator_core_extension import show, hide, Priority
    show("/World/SomePrim", Priority.HIGH, source="my_ext")
"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from .operation import PayloadOperation, OpType, Priority


def _orch():
    from .payload_orchestrator import PayloadOrchestrator
    return PayloadOrchestrator.instance()


def show(prim_path: str,
         priority: Priority = Priority.MEDIUM,
         source: str = "",
         callback: Optional[Callable] = None) -> bool:
    try:
        _orch().request(PayloadOperation(prim_path, OpType.SHOW, priority, source=source, callback=callback))
        return True
    except RuntimeError:
        return False


def hide(prim_path: str,
         priority: Priority = Priority.MEDIUM,
         source: str = "",
         callback: Optional[Callable] = None) -> bool:
    try:
        _orch().request(PayloadOperation(prim_path, OpType.HIDE, priority, source=source, callback=callback))
        return True
    except RuntimeError:
        return False


def show_hide(prim_path: str,
              visible: bool,
              priority: Priority = Priority.MEDIUM,
              source: str = "",
              callback: Optional[Callable] = None) -> bool:
    return show(prim_path, priority, source, callback) if visible else hide(prim_path, priority, source, callback)


def batch_show_hide(items: List[Tuple[str, bool]],
                    priority: Priority = Priority.MEDIUM,
                    source: str = "",
                    group: Optional[str] = None) -> bool:
    """Submit a batch of (prim_path, visible) pairs."""
    try:
        ops = [
            PayloadOperation(path, OpType.SHOW if vis else OpType.HIDE, priority, source=source)
            for path, vis in items
        ]
        _orch().batch(ops, group=group)
        return True
    except RuntimeError:
        return False


def load_prim(prim_path: str,
              priority: Priority = Priority.MEDIUM,
              source: str = "",
              callback: Optional[Callable] = None) -> bool:
    try:
        _orch().request(PayloadOperation(prim_path, OpType.LOAD, priority, source=source, callback=callback))
        return True
    except RuntimeError:
        return False


def unload_prim(prim_path: str,
                priority: Priority = Priority.MEDIUM,
                source: str = "",
                callback: Optional[Callable] = None) -> bool:
    try:
        _orch().request(PayloadOperation(prim_path, OpType.UNLOAD, priority, source=source, callback=callback))
        return True
    except RuntimeError:
        return False
