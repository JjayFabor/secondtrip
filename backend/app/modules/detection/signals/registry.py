"""The complete V1 signal registry."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from app.modules.detection.defaults import DEFAULT_SIGNAL_KEYS
from app.modules.detection.signals.base import CandidatePair, Signal, SignalResult
from app.modules.detection.signals.commercial import (
    LowValueFollowupSignal,
    RepeatPartCodeSignal,
    WarrantyMarkerSignal,
    WithinEquipmentWarrantySignal,
    ZeroValueFollowupSignal,
)
from app.modules.detection.signals.entity import (
    SameCustomerSignal,
    SameEquipmentSignal,
    SameLocationSignal,
    SameServiceCategorySignal,
    SameTechnicianSignal,
)
from app.modules.detection.signals.temporal import DaysBetweenSignal, RecurrenceDensitySignal
from app.modules.detection.signals.vetoes import (
    PlannedMultivisitSignal,
    ScheduledMaintenanceSignal,
)

_SIGNALS: tuple[Signal[CandidatePair], ...] = (
    SameCustomerSignal(),
    SameLocationSignal(),
    SameEquipmentSignal(),
    DaysBetweenSignal(),
    SameServiceCategorySignal(),
    ZeroValueFollowupSignal(),
    LowValueFollowupSignal(),
    WarrantyMarkerSignal(),
    WithinEquipmentWarrantySignal(),
    SameTechnicianSignal(),
    RepeatPartCodeSignal(),
    RecurrenceDensitySignal(),
    ScheduledMaintenanceSignal(),
    PlannedMultivisitSignal(),
)
SIGNAL_REGISTRY: Mapping[str, Signal[CandidatePair]] = MappingProxyType(
    {signal.key: signal for signal in _SIGNALS}
)

if set(SIGNAL_REGISTRY) != DEFAULT_SIGNAL_KEYS:
    raise RuntimeError("signal registry and code-owned signal catalogue differ")


def evaluate_signals(
    pair: CandidatePair,
    configured_params: Mapping[str, dict[str, object]],
) -> list[SignalResult]:
    unknown = sorted(set(configured_params) - SIGNAL_REGISTRY.keys())
    if unknown:
        raise ValueError(f"configured rules have no signal implementation: {unknown}")
    return [
        SIGNAL_REGISTRY[key].evaluate(pair, params) for key, params in configured_params.items()
    ]
