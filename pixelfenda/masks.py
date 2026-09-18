from __future__ import annotations

import math
import cv2
import numpy as np


MASK_MODES = {
    "full": "Tela inteira",
    "rectangle": "Retângulo",
    "ellipse": "Elipse",
    "linear": "Gradiente linear",
    "vignette": "Vinheta / centro",
}
MASK_BY_LABEL = {v: k for k, v in MASK_MODES.items()}


def _blur_mask(mask: np.ndarray, feather: float, width: int, height: int) -> np.ndarray:
    f = float(np.clip(feather, 0.0, 1.0))
    if f <= 1e-4:
        return mask.astype(np.float32, copy=False)
    sigma = max(0.6, f * min(width, height) * 0.12)
    blurred = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigmaX=sigma, sigmaY=sigma)
    m = float(blurred.max())
    if m > 1e-8:
        blurred /= m
    return np.clip(blurred, 0.0, 1.0)


def build_mask(width: int, height: int, spec, center_override: tuple[float, float] | None = None) -> np.ndarray:
    kind = str(getattr(spec, "mask_kind", "full"))
    if kind == "full":
        mask = np.ones((height, width), dtype=np.float32)
    else:
        cx = float(getattr(spec, "mask_x", 0.5))
        cy = float(getattr(spec, "mask_y", 0.5))
        if center_override is not None:
            cx, cy = center_override
        mw = float(np.clip(getattr(spec, "mask_w", 0.6), 0.01, 1.5))
        mh = float(np.clip(getattr(spec, "mask_h", 0.6), 0.01, 1.5))
        feather = float(np.clip(getattr(spec, "mask_feather", 0.08), 0.0, 1.0))
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        x = xx / max(1.0, width - 1.0)
        y = yy / max(1.0, height - 1.0)
        if kind == "rectangle":
            x0, x1 = cx - mw * 0.5, cx + mw * 0.5
            y0, y1 = cy - mh * 0.5, cy + mh * 0.5
            mask = ((x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)).astype(np.float32)
            mask = _blur_mask(mask, feather, width, height)
        elif kind == "ellipse":
            dx = (x - cx) / max(0.005, mw * 0.5)
            dy = (y - cy) / max(0.005, mh * 0.5)
            dist = np.sqrt(dx * dx + dy * dy)
            if feather <= 1e-4:
                mask = (dist <= 1.0).astype(np.float32)
            else:
                edge = max(0.02, feather * 0.75)
                mask = np.clip((1.0 + edge - dist) / edge, 0.0, 1.0).astype(np.float32)
        elif kind == "linear":
            angle = math.radians(float(getattr(spec, "mask_angle", 0.0)))
            axis = (x - cx) * math.cos(angle) + (y - cy) * math.sin(angle)
            softness = max(0.02, feather * 0.7 + 0.04)
            mask = np.clip(0.5 + axis / softness, 0.0, 1.0).astype(np.float32)
        elif kind == "vignette":
            dx = (x - cx) / max(0.005, mw * 0.5)
            dy = (y - cy) / max(0.005, mh * 0.5)
            dist = np.sqrt(dx * dx + dy * dy)
            edge = max(0.03, feather * 0.9 + 0.08)
            mask = np.clip((1.0 + edge - dist) / edge, 0.0, 1.0).astype(np.float32)
        else:
            mask = np.ones((height, width), dtype=np.float32)
    if bool(getattr(spec, "mask_invert", False)):
        mask = 1.0 - mask
    return np.clip(mask, 0.0, 1.0).astype(np.float32)


class MaskTracker:
    """Lightweight local mask tracker using pyramidal Lucas-Kanade optical flow.

    It tracks visual feature points inside a rectangular/elliptical region and moves
    only the mask center. This keeps PixelFenda dependency-light while allowing a
    spatial effect to follow a subject/object through ordinary camera motion.
    """

    def __init__(self, width: int, height: int, spec) -> None:
        self.width, self.height = int(width), int(height)
        self.center = (float(getattr(spec, "mask_x", 0.5)), float(getattr(spec, "mask_y", 0.5)))
        self.prev_gray: np.ndarray | None = None
        self.points: np.ndarray | None = None
        self.last_ok = False

    def reset(self, spec) -> None:
        self.center = (float(getattr(spec, "mask_x", 0.5)), float(getattr(spec, "mask_y", 0.5)))
        self.prev_gray = None
        self.points = None
        self.last_ok = False

    def _roi_mask(self, spec) -> np.ndarray:
        class _Proxy:
            pass
        p = _Proxy()
        for name in ("mask_kind", "mask_x", "mask_y", "mask_w", "mask_h", "mask_feather", "mask_invert", "mask_angle"):
            setattr(p, name, getattr(spec, name, None))
        p.mask_kind = "ellipse" if str(getattr(spec, "mask_kind", "full")) == "ellipse" else "rectangle"
        p.mask_x, p.mask_y = self.center
        p.mask_feather = 0.0
        p.mask_invert = False
        return (build_mask(self.width, self.height, p) > 0.5).astype(np.uint8) * 255

    def _reseed(self, gray: np.ndarray, spec) -> None:
        roi = self._roi_mask(spec)
        self.points = cv2.goodFeaturesToTrack(
            gray, maxCorners=80, qualityLevel=0.015, minDistance=6, mask=roi,
            blockSize=5, useHarrisDetector=False,
        )

    def update(self, frame_bgr: np.ndarray, spec) -> tuple[float, float]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if self.prev_gray is None:
            self.prev_gray = gray
            self._reseed(gray, spec)
            return self.center
        if self.points is None or len(self.points) < 5:
            self._reseed(self.prev_gray, spec)
        if self.points is None or len(self.points) < 3:
            self.prev_gray = gray
            self._reseed(gray, spec)
            return self.center
        nxt, status, _err = cv2.calcOpticalFlowPyrLK(
            self.prev_gray, gray, self.points, None,
            winSize=(21, 21), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
        )
        if nxt is None or status is None:
            self.prev_gray = gray
            self._reseed(gray, spec)
            return self.center
        good_old = self.points[status.reshape(-1) == 1].reshape(-1, 2)
        good_new = nxt[status.reshape(-1) == 1].reshape(-1, 2)
        if len(good_new) >= 3:
            delta = np.median(good_new - good_old, axis=0)
            strength = float(np.clip(getattr(spec, "mask_track_strength", 1.0), 0.0, 1.0))
            dx = float(delta[0] / max(1, self.width)) * strength
            dy = float(delta[1] / max(1, self.height)) * strength
            cx = float(np.clip(self.center[0] + dx, 0.0, 1.0))
            cy = float(np.clip(self.center[1] + dy, 0.0, 1.0))
            self.center = (cx, cy)
            self.points = good_new.reshape(-1, 1, 2)
            self.last_ok = True
        else:
            self.last_ok = False
            self.points = None
        self.prev_gray = gray
        if self.points is None or len(self.points) < 12:
            self._reseed(gray, spec)
        return self.center
