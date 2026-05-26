"""Datatypes emitted by :class:`~.loader.ConfigLoader`."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

BoundsType = Tuple[Tuple[float, float, float], Tuple[float, float, float]]


@dataclass
class SpatialTriggerSpec:
    """Kwargs forwarded to ``SpatialTriggerService.add_trigger``."""

    trigger_id: str
    position: Tuple[float, float, float]
    trigger_type: str
    radius: float
    radius_meters: Optional[float]
    xz_only: bool
    one_shot: bool
    activation: str
    behaviors: list
    bounds: Optional[BoundsType]
    active: bool


@dataclass
class LoadedConfig:
    """Parsed output of one ``interactions.json`` reload."""

    all_points: list = field(default_factory=list)
    projectable_points: list = field(default_factory=list)
    click_points_by_path: dict = field(default_factory=dict)

    meters_per_unit: float = 0.01
    spatial_triggers: List[SpatialTriggerSpec] = field(default_factory=list)
    npc_registry: dict = field(default_factory=dict)
    icon_registry: dict = field(default_factory=dict)
    npc_marker_paths: list = field(default_factory=list)
    icon_marker_paths: list = field(default_factory=list)
    # POI coins: list of ``(coin_xform_prim_path, spin_axis)`` tuples where
    # ``spin_axis`` is the name of the ``xformOp:rotate{X|Y|Z}:spin`` op
    # authored on ``<coin_xform_prim_path>/CoinModel`` by
    # :func:`session_authoring.attach_coin_payload`. The marker service
    # animates that op per frame in mode ``"coin"``.
    coin_marker_paths: List[Tuple[str, str]] = field(default_factory=list)
