from __future__ import annotations

import cv2
import numpy as np


class FilterEngine:
    def __init__(self, width: int, height: int, seed: int = 1337) -> None:
        self.width = width
        self.height = height
        self.rng = np.random.default_rng(seed)
        y, x = np.ogrid[:height, :width]
        cx, cy = (width - 1) / 2.0, (height - 1) / 2.0
        nx = (x - cx) / max(1.0, width * 0.5)
        ny = (y - cy) / max(1.0, height * 0.5)
        self.radius = np.sqrt(nx * nx + ny * ny).astype(np.float32)

    @staticmethod
    def _basic(img: np.ndarray, contrast: float = 1.0, saturation: float = 1.0,
               lift: float = 0.0, gamma: float = 1.0, gains=(1.0, 1.0, 1.0)) -> np.ndarray:
        f = img.astype(np.float32) / 255.0
        f = np.clip((f - 0.5) * contrast + 0.5 + lift, 0.0, 1.0)
        if gamma != 1.0:
            f = np.power(np.clip(f, 0.0, 1.0), 1.0 / max(0.05, gamma))
        lum = f[..., 0] * 0.114 + f[..., 1] * 0.587 + f[..., 2] * 0.299
        f = lum[..., None] + (f - lum[..., None]) * saturation
        f *= np.array(gains, dtype=np.float32)[None, None, :]
        return np.clip(f * 255.0, 0, 255).astype(np.uint8)

    @staticmethod
    def _split_tone(img: np.ndarray, shadows_bgr, highlights_bgr, amount: float) -> np.ndarray:
        f = img.astype(np.float32) / 255.0
        lum = np.mean(f, axis=2, keepdims=True)
        sh = np.clip(1.0 - lum * 2.0, 0.0, 1.0)
        hi = np.clip((lum - 0.5) * 2.0, 0.0, 1.0)
        sb = np.array(shadows_bgr, dtype=np.float32).reshape(1, 1, 3)
        hb = np.array(highlights_bgr, dtype=np.float32).reshape(1, 1, 3)
        f = f + (sb - 0.5) * sh * amount + (hb - 0.5) * hi * amount
        return np.clip(f * 255.0, 0, 255).astype(np.uint8)

    def _grain(self, img: np.ndarray, amount: float, monochrome: bool = True) -> np.ndarray:
        if amount <= 0:
            return img
        h, w = img.shape[:2]
        if monochrome:
            n = self.rng.normal(0.0, amount * 16.0, (h, w, 1)).astype(np.float32)
        else:
            n = self.rng.normal(0.0, amount * 12.0, (h, w, 3)).astype(np.float32)
        return np.clip(img.astype(np.float32) + n, 0, 255).astype(np.uint8)

    def _vignette(self, img: np.ndarray, amount: float) -> np.ndarray:
        if amount <= 0:
            return img
        mask = 1.0 - np.clip((self.radius - 0.35) / 0.9, 0.0, 1.0) * amount
        return np.clip(img.astype(np.float32) * mask[..., None], 0, 255).astype(np.uint8)

    @staticmethod
    def _bloom(img: np.ndarray, threshold: int = 185, amount: float = 0.25, warm: bool = False) -> np.ndarray:
        lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = np.maximum(lum.astype(np.int16) - threshold, 0).astype(np.uint8)
        bright = cv2.bitwise_and(img, img, mask=mask)
        sigma = max(1.0, min(img.shape[:2]) / 120.0)
        blur = cv2.GaussianBlur(bright, (0, 0), sigmaX=sigma, sigmaY=sigma)
        if warm:
            blur = blur.astype(np.float32)
            blur[..., 2] *= 1.18
            blur[..., 0] *= 0.82
            blur = np.clip(blur, 0, 255).astype(np.uint8)
        return cv2.addWeighted(img, 1.0, blur, amount, 0)

    @staticmethod
    def _gray(img: np.ndarray) -> np.ndarray:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)

    def apply(self, frame: np.ndarray, key: str, intensity: float = 1.0, frame_index: int = 0) -> np.ndarray:
        if key == "none" or intensity <= 0:
            return frame
        t = float(np.clip(intensity, 0.0, 1.0))
        src = frame

        if key == "vintage_70":
            out = self._basic(src, 0.88, 0.78, 0.035, 0.97, (0.90, 1.00, 1.11))
            out = self._split_tone(out, (0.34, 0.38, 0.44), (0.52, 0.58, 0.68), 0.13)
            out = self._grain(out, 0.32)
            out = self._vignette(out, 0.28)
        elif key == "vintage_90":
            out = self._basic(src, 0.94, 0.82, 0.02, 0.98, (0.96, 1.04, 1.04))
            out = self._split_tone(out, (0.44, 0.49, 0.38), (0.53, 0.46, 0.59), 0.12)
            out = self._grain(out, 0.26, monochrome=False)
        elif key == "cinematic_teal_amber":
            out = self._basic(src, 1.10, 1.02, -0.01, 1.02)
            out = self._split_tone(out, (0.62, 0.50, 0.34), (0.38, 0.53, 0.68), 0.24)
            out = self._vignette(out, 0.18)
        elif key == "cold_archive":
            out = self._basic(src, 0.93, 0.58, 0.025, 0.96, (1.10, 1.03, 0.88))
            out = self._grain(out, 0.36)
            out = self._vignette(out, 0.30)
            # subtle projector exposure breathing
            flicker = 0.985 + 0.018 * np.sin(frame_index * 0.37)
            out = np.clip(out.astype(np.float32) * flicker, 0, 255).astype(np.uint8)
        elif key == "silver_gray":
            out = self._gray(src)
            out = self._basic(out, 1.08, 0.0, 0.0, 1.0, (1.03, 1.01, 0.98))
            out = self._grain(out, 0.20)
        elif key == "noir":
            out = self._gray(src)
            out = self._basic(out, 1.38, 0.0, -0.035, 0.96)
            out = self._vignette(out, 0.40)
            out = self._grain(out, 0.22)
        elif key == "odyssey_70":
            # Authorial emulation: large-format clarity, restrained saturation,
            # warm photochemical highlights, neutral/cool shadows and fine grain.
            out = self._basic(src, 1.06, 0.91, -0.008, 1.015, (1.015, 1.00, 1.025))
            out = self._split_tone(out, (0.56, 0.52, 0.46), (0.46, 0.51, 0.59), 0.10)
            out = self._bloom(out, 208, 0.11, warm=True)
            out = self._grain(out, 0.13)
            out = self._vignette(out, 0.09)
        elif key == "bleach_bypass":
            gray = self._gray(src)
            out = cv2.addWeighted(src, 0.42, gray, 0.58, 0)
            out = self._basic(out, 1.28, 0.52, -0.015, 1.0)
            out = self._grain(out, 0.20)
        elif key == "matrix_green":
            g = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            out = np.zeros_like(src)
            out[..., 1] = np.clip((g ** 0.85) * 255, 0, 255).astype(np.uint8)
            out[..., 0] = np.clip(g * 42, 0, 255).astype(np.uint8)
            out[..., 2] = np.clip(g * 18, 0, 255).astype(np.uint8)
            out = self._basic(out, 1.20, 1.0, -0.02, 0.95)
        elif key == "gothic_iron":
            out = self._basic(src, 1.20, 0.62, -0.035, 0.94, (1.06, 0.94, 1.02))
            out = self._split_tone(out, (0.45, 0.45, 0.52), (0.34, 0.36, 0.58), 0.18)
            out = self._vignette(out, 0.34)
        elif key == "y2k_chrome":
            out = self._basic(src, 1.10, 0.50, 0.045, 1.05, (1.08, 1.05, 1.00))
            out = self._split_tone(out, (0.60, 0.56, 0.54), (0.61, 0.59, 0.57), 0.12)
            out = self._bloom(out, 190, 0.18)
        elif key == "dream_white":
            out = self._basic(src, 0.78, 0.55, 0.10, 1.06, (1.03, 1.02, 1.04))
            out = self._bloom(out, 155, 0.30)
        elif key == "neon_night":
            out = self._basic(src, 1.17, 1.18, -0.04, 0.94, (1.16, 1.02, 0.92))
            out = self._split_tone(out, (0.64, 0.51, 0.35), (0.46, 0.48, 0.64), 0.22)
            out = self._bloom(out, 178, 0.22)
        elif key == "space_blue":
            out = self._basic(src, 1.16, 0.72, -0.035, 0.92, (1.18, 1.05, 0.80))
            out = self._grain(out, 0.18)
            out = self._vignette(out, 0.28)
        elif key == "antique_sepia":
            g = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY).astype(np.float32)
            out = np.dstack([g * 0.72, g * 0.88, g * 1.06])
            out = np.clip(out, 0, 255).astype(np.uint8)
            out = self._grain(out, 0.30)
            out = self._vignette(out, 0.36)
        elif key == "social_cool":
            out = self._basic(src, 1.13, 1.08, 0.01, 1.02, (1.07, 1.02, 0.97))
        elif key == "muted_linen":
            out = self._basic(src, 0.86, 0.67, 0.06, 1.02, (0.98, 1.00, 1.04))
            out = self._grain(out, 0.08)
        elif key == "soft_bw":
            out = self._gray(src)
            out = self._basic(out, 0.90, 0.0, 0.025, 1.03)
            out = self._grain(out, 0.10)
        elif key == "infrared_ice":
            g = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            inv = 1.0 - g
            out = np.dstack([np.clip(inv*1.12,0,1), np.clip(inv*0.92 + g*0.20,0,1), np.clip(inv*0.70 + g*0.35,0,1)])
            out = np.clip(out*255.0,0,255).astype(np.uint8)
            out = self._basic(out, 1.18, 0.86, 0.015, 1.02)
            out = self._grain(out, 0.14)
        else:
            return src

        if t >= 0.999:
            return out
        return cv2.addWeighted(src, 1.0 - t, out, t, 0)
