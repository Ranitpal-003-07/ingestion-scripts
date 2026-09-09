"""Controllable metric scenarios for PromQL alert testing."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from nr_metrics import config

if TYPE_CHECKING:
    from nr_metrics.otlp import OtlpMetricsSession

MODES = config.MODES


@dataclass
class SeriesState:
    labels: dict[str, str]
    up: float = 1.0
    cpu_ratio: float = 0.3
    memory_ratio: float = 0.35
    requests_per_tick: int = 12
    errors_per_tick: int = 0
    latency_seconds: float = 0.05


@dataclass
class ScenarioState:
    mode: str = "baseline"
    target: dict[str, str] = field(default_factory=dict)
    series: list[SeriesState] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.series:
            self.series = [
                SeriesState(labels=dict(labels)) for labels in config.SERIES
            ]
        self.apply_mode()

    def set_mode(self, mode: str, target: dict[str, str] | None = None) -> None:
        if mode not in MODES:
            raise ValueError(f"Unknown mode {mode!r}; expected one of {MODES}")
        self.mode = "baseline" if mode == "recover" else mode
        if target is not None:
            self.target = target
        self.apply_mode()

    def matches_target(self, labels: dict[str, str]) -> bool:
        if not self.target:
            return True
        for key, value in self.target.items():
            if labels.get(key) != value:
                return False
        return True

    def apply_mode(self) -> None:
        for series in self.series:
            labels = series.labels
            targeted = self.matches_target(labels)
            is_baseline = self.mode == "baseline" or not targeted

            if is_baseline:
                series.up = 1.0
                series.cpu_ratio = _baseline_cpu(labels)
                series.memory_ratio = _baseline_memory(labels)
                # Keep a low non-zero error rate so demo_http_errors_total stream exists.
                series.requests_per_tick = 40
                series.errors_per_tick = 1
                series.latency_seconds = random.uniform(0.02, 0.08)
                continue

            if self.mode == "spike_cpu":
                series.cpu_ratio = random.uniform(0.95, 0.99)
                series.memory_ratio = _baseline_memory(labels)
                series.up = 1.0
                series.requests_per_tick = 12
                series.errors_per_tick = 0
                series.latency_seconds = random.uniform(0.02, 0.08)
            elif self.mode == "spike_errors":
                series.cpu_ratio = _baseline_cpu(labels)
                series.memory_ratio = _baseline_memory(labels)
                series.up = 1.0
                series.requests_per_tick = 20
                series.errors_per_tick = 8
                series.latency_seconds = random.uniform(0.02, 0.08)
            elif self.mode == "spike_latency":
                series.cpu_ratio = _baseline_cpu(labels)
                series.memory_ratio = _baseline_memory(labels)
                series.up = 1.0
                series.requests_per_tick = 15
                series.errors_per_tick = 0
                series.latency_seconds = random.uniform(1.2, 2.5)
            elif self.mode == "down":
                series.up = 0.0
                series.cpu_ratio = 0.0
                series.memory_ratio = _baseline_memory(labels)
                series.requests_per_tick = 0
                series.errors_per_tick = 0
                series.latency_seconds = 0.0


def _baseline_cpu(labels: dict[str, str]) -> float:
    base = {
        "demo-api": 0.28,
        "demo-orders": 0.32,
        "demo-payments": 0.25,
    }
    jitter = 0.05 if labels["instance"].endswith("-1") else 0.08
    return base[labels["service"]] + random.uniform(-0.03, jitter)


def _baseline_memory(labels: dict[str, str]) -> float:
    base = {
        "demo-api": 0.38,
        "demo-orders": 0.42,
        "demo-payments": 0.36,
    }
    return base[labels["service"]] + random.uniform(-0.04, 0.06)


def emit_tick(session: OtlpMetricsSession, state: ScenarioState) -> None:
    """Record one emission tick for all series."""
    for series in state.series:
        attrs = dict(series.labels)
        session.record_gauges(
            up=series.up,
            cpu_ratio=series.cpu_ratio,
            memory_ratio=series.memory_ratio,
            attributes=attrs,
        )
        session.record_requests(series.requests_per_tick, attributes=attrs)
        session.record_errors(series.errors_per_tick, attributes=attrs)
        if series.latency_seconds > 0:
            session.record_latency(series.latency_seconds, attributes=attrs)

    session.flush()
