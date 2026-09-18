from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import cv2
import numpy as np


@dataclass
class SceneEvent:
    frame: int
    seconds: float
    score: float


class SceneCutDetector:
    """Lightweight HSV content-change detector.

    It follows the same general family as content-aware cut detection: compare
    adjacent frames after reducing them to a small HSV representation. It is kept
    internal so the base PixelFenda install does not require another package.
    """

    def __init__(self, threshold: float = 0.22, min_gap_frames: int = 8, width: int = 160, height: int = 90) -> None:
        self.threshold = float(np.clip(threshold, 0.03, 0.95))
        self.min_gap_frames = max(1, int(min_gap_frames))
        self.width, self.height = int(width), int(height)
        self.prev: np.ndarray | None = None
        self.frame_index = -1
        self.last_cut = -10_000
        self.pulse = 0.0

    def reset(self) -> None:
        self.prev = None
        self.frame_index = -1
        self.last_cut = -10_000
        self.pulse = 0.0

    def update(self, frame_bgr: np.ndarray) -> tuple[bool, float, float]:
        self.frame_index += 1
        small = cv2.resize(frame_bgr, (self.width, self.height), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).astype(np.float32)
        if self.prev is None:
            self.prev = hsv
            return False, 0.0, 0.0
        d = np.abs(hsv - self.prev)
        # Hue wraps at 180 in OpenCV; use shortest circular distance.
        dh = np.minimum(d[..., 0], 180.0 - d[..., 0]) / 90.0
        ds = d[..., 1] / 255.0
        dv = d[..., 2] / 255.0
        score = float(np.mean(dh) * 0.35 + np.mean(ds) * 0.25 + np.mean(dv) * 0.40)
        self.prev = hsv
        gap_ok = (self.frame_index - self.last_cut) >= self.min_gap_frames
        cut = bool(score >= self.threshold and gap_ok)
        if cut:
            self.last_cut = self.frame_index
            self.pulse = 1.0
        else:
            self.pulse *= 0.84
            if self.pulse < 0.002:
                self.pulse = 0.0
        return cut, score, float(self.pulse)


def analyze_scenes(
    path: str,
    threshold: float = 0.22,
    max_seconds: float | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> list[SceneEvent]:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Não foi possível abrir o vídeo para análise de cenas: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if max_seconds and max_seconds > 0:
        cap_total = int(round(max_seconds * fps))
        total = min(total, cap_total) if total else cap_total
    detector = SceneCutDetector(threshold=threshold, min_gap_frames=max(4, int(round(fps * 0.18))))
    events: list[SceneEvent] = [SceneEvent(0, 0.0, 0.0)]
    i = 0
    try:
        while True:
            if total and i >= total:
                break
            ok, frame = cap.read()
            if not ok:
                break
            cut, score, _pulse = detector.update(frame)
            if cut:
                events.append(SceneEvent(i, i / fps, score))
            i += 1
            if progress and (i == 1 or i % max(1, int(fps)) == 0):
                progress(min(1.0, i / max(1, total or i)), f"Analisando cenas · quadro {i}/{total or '?'}")
    finally:
        cap.release()
    return events
