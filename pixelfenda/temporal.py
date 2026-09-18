from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
import math

import numpy as np


EASING_MODES = {
    "linear": "Linear",
    "smooth": "Suave (smoothstep)",
    "ease_in": "Acelerar",
    "ease_out": "Desacelerar",
    "hold": "Hold / degrau",
}
EASING_BY_LABEL = {v: k for k, v in EASING_MODES.items()}


@dataclass(frozen=True)
class TemporalValues:
    active: bool
    intensity: float
    opacity: float
    mod_amount: float
    window_gain: float


def _curve(x: float, mode: str) -> float:
    x = float(np.clip(x, 0.0, 1.0))
    if mode == "hold":
        return 0.0
    if mode == "ease_in":
        return x * x
    if mode == "ease_out":
        return 1.0 - (1.0 - x) * (1.0 - x)
    if mode == "smooth":
        return x * x * (3.0 - 2.0 * x)
    return x


def _points_for_property(
    keyframes: Iterable[dict[str, Any]],
    prop: str,
    base: float,
    duration: float,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = [(0.0, float(base))]
    for raw in keyframes:
        if prop not in raw:
            continue
        try:
            t = max(0.0, float(raw.get("time", raw.get("t", 0.0))))
            value = float(raw[prop])
        except (TypeError, ValueError):
            continue
        points.append((t, float(np.clip(value, 0.0, 1.0))))
    if duration > 0:
        points.append((duration, points[-1][1] if len(points) > 1 else float(base)))
    points.sort(key=lambda p: p[0])
    # Last keyframe wins when two occupy the same time.
    compact: list[tuple[float, float]] = []
    for p in points:
        if compact and abs(compact[-1][0] - p[0]) < 1e-9:
            compact[-1] = p
        else:
            compact.append(p)
    return compact


def evaluate_property(
    keyframes: Iterable[dict[str, Any]],
    prop: str,
    base: float,
    time_s: float,
    duration: float,
    easing: str = "smooth",
) -> float:
    pts = _points_for_property(keyframes, prop, base, duration)
    if len(pts) == 1:
        return float(np.clip(pts[0][1], 0.0, 1.0))
    t = max(0.0, float(time_s))
    if t <= pts[0][0]:
        return pts[0][1]
    if t >= pts[-1][0]:
        return pts[-1][1]
    for (ta, va), (tb, vb) in zip(pts, pts[1:]):
        if ta <= t <= tb:
            if tb <= ta:
                return vb
            u = _curve((t - ta) / (tb - ta), easing)
            return float(np.clip(va + (vb - va) * u, 0.0, 1.0))
    return float(np.clip(base, 0.0, 1.0))


def temporal_values(spec, time_s: float, duration: float) -> TemporalValues:
    start = max(0.0, float(getattr(spec, "start_s", 0.0)))
    raw_end = float(getattr(spec, "end_s", -1.0))
    end = duration if raw_end < 0.0 else raw_end
    if duration > 0:
        end = min(end, duration)
    if end < start:
        end = start
    t = float(time_s)
    if t < start or t > end:
        return TemporalValues(False, 0.0, 0.0, 0.0, 0.0)

    fade_in = max(0.0, float(getattr(spec, "fade_in_s", 0.0)))
    fade_out = max(0.0, float(getattr(spec, "fade_out_s", 0.0)))
    gain = 1.0
    if fade_in > 0.0:
        gain *= float(np.clip((t - start) / fade_in, 0.0, 1.0))
    if fade_out > 0.0:
        gain *= float(np.clip((end - t) / fade_out, 0.0, 1.0))
    gain = gain * gain * (3.0 - 2.0 * gain)  # smooth window edges

    keyframes = list(getattr(spec, "keyframes", []) or [])
    easing = str(getattr(spec, "keyframe_ease", "smooth"))
    intensity = evaluate_property(keyframes, "intensity", float(spec.intensity), t, duration, easing)
    opacity = evaluate_property(keyframes, "opacity", float(spec.opacity), t, duration, easing) * gain
    mod_amount = evaluate_property(keyframes, "mod_amount", float(spec.mod_amount), t, duration, easing)
    return TemporalValues(True, intensity, float(np.clip(opacity, 0.0, 1.0)), mod_amount, gain)


def normalize_keyframes(items: Iterable[dict[str, Any]]) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for raw in items:
        try:
            t = max(0.0, float(raw.get("time", raw.get("t", 0.0))))
        except (TypeError, ValueError):
            continue
        row: dict[str, float] = {"time": t}
        for key in ("intensity", "opacity", "mod_amount"):
            if key in raw:
                try:
                    row[key] = float(np.clip(float(raw[key]), 0.0, 1.0))
                except (TypeError, ValueError):
                    pass
        if len(row) > 1:
            out.append(row)
    out.sort(key=lambda x: x["time"])
    return out


def make_beat_pulse_keyframes(
    beat_times: Iterable[float],
    *,
    base_intensity: float,
    peak_intensity: float = 1.0,
    decay_s: float = 0.12,
    duration: float | None = None,
    max_beats: int = 300,
) -> list[dict[str, float]]:
    """Create deterministic intensity pulses centered on detected beats."""
    base = float(np.clip(base_intensity, 0.0, 1.0))
    peak = float(np.clip(peak_intensity, 0.0, 1.0))
    decay = max(0.01, float(decay_s))
    out: list[dict[str, float]] = [{"time": 0.0, "intensity": base}]
    count = 0
    for bt in beat_times:
        t = max(0.0, float(bt))
        if duration is not None and t > duration:
            break
        if count >= max_beats:
            break
        pre = max(0.0, t - min(0.035, decay * 0.25))
        out.extend([
            {"time": pre, "intensity": base},
            {"time": t, "intensity": peak},
            {"time": t + decay, "intensity": base},
        ])
        count += 1
    return normalize_keyframes(out)
