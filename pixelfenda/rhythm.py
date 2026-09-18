from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import os

import cv2
import numpy as np

from .reactive import AudioReactiveTrack


@dataclass
class BeatAnalysis:
    bpm: float
    beat_times: list[float]
    duration: float
    frames: int


def detect_beats_from_track(track: AudioReactiveTrack, fps: float, duration: float) -> BeatAnalysis:
    if track.features.size == 0:
        return BeatAnalysis(0.0, [], duration, 0)
    onset = track.features[:, 4].astype(np.float32)
    # Adaptive threshold: strong local transients + refractory period.
    threshold = max(0.28, float(np.percentile(onset, 72)) * 0.85)
    min_gap = max(1, int(round(fps * 0.24)))
    candidates: list[int] = []
    last = -min_gap
    for i in range(1, len(onset) - 1):
        if onset[i] < threshold or onset[i] < onset[i - 1] or onset[i] < onset[i + 1]:
            continue
        if i - last < min_gap:
            # Within refractory window retain the stronger peak.
            if candidates and onset[i] > onset[candidates[-1]]:
                candidates[-1] = i
                last = i
            continue
        candidates.append(i)
        last = i
    times = [i / fps for i in candidates]
    bpm = 0.0
    if len(times) >= 3:
        intervals = np.diff(np.asarray(times, dtype=np.float64))
        intervals = intervals[(intervals >= 0.24) & (intervals <= 1.5)]
        if intervals.size:
            med = float(np.median(intervals))
            bpm = 60.0 / med if med > 1e-6 else 0.0
            # Fold common half/double-time ambiguity into a musical 70–180 BPM band.
            while bpm < 70.0:
                bpm *= 2.0
            while bpm > 180.0:
                bpm *= 0.5
    return BeatAnalysis(float(bpm), times, float(duration), int(len(track.features)))


def analyze_beats(
    media_path: str,
    fps: float,
    total_frames: int,
    *,
    loop: bool = False,
    progress: Callable[[float, str], None] | None = None,
) -> BeatAnalysis:
    if not media_path or not os.path.isfile(media_path):
        raise ValueError("Arquivo de mídia inválido para análise de batidas.")
    if progress:
        progress(0.05, "Decodificando e analisando áudio")
    track = AudioReactiveTrack.from_media(media_path, fps, total_frames, loop=loop)
    duration = total_frames / max(1.0, fps)
    result = detect_beats_from_track(track, fps, duration)
    if loop and result.beat_times and len(track.features) < total_frames:
        base_duration = len(track.features) / max(1.0, fps)
        if base_duration > 1e-6:
            repeated: list[float] = []
            offset = 0.0
            while offset < duration and len(repeated) < 5000:
                for t in result.beat_times:
                    tt = t + offset
                    if tt > duration:
                        break
                    repeated.append(tt)
                offset += base_duration
            result = BeatAnalysis(result.bpm, repeated, duration, total_frames)
    if progress:
        progress(1.0, f"Grade de batidas concluída · {len(result.beat_times)} beats · {result.bpm:.1f} BPM")
    return result
