from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np

from .builtin_luts import ensure_builtin_lut


@dataclass
class CubeLUT:
    title: str
    kind: str
    size: int
    data: np.ndarray
    domain_min: np.ndarray
    domain_max: np.ndarray

    @classmethod
    def load(cls, path: str | Path) -> "CubeLUT":
        p = ensure_builtin_lut(Path(path))
        title = p.stem
        size_3d: int | None = None
        size_1d: int | None = None
        domain_min = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        domain_max = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        rows: list[list[float]] = []
        for raw in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            upper = line.upper()
            if upper.startswith("TITLE"):
                q = line.split(None, 1)
                if len(q) == 2:
                    title = q[1].strip().strip('"')
            elif upper.startswith("LUT_3D_SIZE"):
                size_3d = int(line.split()[-1])
            elif upper.startswith("LUT_1D_SIZE"):
                size_1d = int(line.split()[-1])
            elif upper.startswith("DOMAIN_MIN"):
                domain_min = np.array([float(x) for x in line.split()[1:4]], dtype=np.float32)
            elif upper.startswith("DOMAIN_MAX"):
                domain_max = np.array([float(x) for x in line.split()[1:4]], dtype=np.float32)
            else:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
                    except ValueError:
                        pass
        if size_3d:
            expected = size_3d ** 3
            if len(rows) < expected:
                raise ValueError(f"LUT 3D incompleta: esperadas {expected} linhas, encontradas {len(rows)}.")
            arr = np.asarray(rows[:expected], dtype=np.float32).reshape(size_3d, size_3d, size_3d, 3)
            # .cube ordering uses R as the fastest-changing coordinate, so the
            # reshaped axes are B, G, R.
            return cls(title, "3d", size_3d, arr, domain_min, domain_max)
        if size_1d:
            if len(rows) < size_1d:
                raise ValueError(f"LUT 1D incompleta: esperadas {size_1d} linhas, encontradas {len(rows)}.")
            return cls(title, "1d", size_1d, np.asarray(rows[:size_1d], dtype=np.float32), domain_min, domain_max)
        raise ValueError("Arquivo .cube sem LUT_3D_SIZE ou LUT_1D_SIZE.")

    def apply(self, frame_bgr: np.ndarray, intensity: float = 1.0) -> np.ndarray:
        t = float(np.clip(intensity, 0.0, 1.0))
        if t <= 0.0:
            return frame_bgr
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        den = np.maximum(1e-7, self.domain_max - self.domain_min)
        x = np.clip((rgb - self.domain_min[None, None, :]) / den[None, None, :], 0.0, 1.0)
        if self.kind == "1d":
            pos = x * (self.size - 1)
            i0 = np.floor(pos).astype(np.int32)
            i1 = np.minimum(i0 + 1, self.size - 1)
            f = pos - i0
            out = np.empty_like(x)
            for c in range(3):
                out[..., c] = self.data[i0[..., c], c] * (1.0 - f[..., c]) + self.data[i1[..., c], c] * f[..., c]
        else:
            h, w = x.shape[:2]
            out = np.empty_like(x)
            # Chunk rows to avoid allocating eight full-HD corner volumes at once.
            for y0 in range(0, h, 96):
                y1 = min(h, y0 + 96)
                q = x[y0:y1]
                pos = q * (self.size - 1)
                lo = np.floor(pos).astype(np.int32)
                hi = np.minimum(lo + 1, self.size - 1)
                frac = pos - lo
                r0, g0, b0 = lo[..., 0], lo[..., 1], lo[..., 2]
                r1, g1, b1 = hi[..., 0], hi[..., 1], hi[..., 2]
                fr, fg, fb = frac[..., 0:1], frac[..., 1:2], frac[..., 2:3]
                d = self.data
                c000 = d[b0, g0, r0]; c100 = d[b0, g0, r1]
                c010 = d[b0, g1, r0]; c110 = d[b0, g1, r1]
                c001 = d[b1, g0, r0]; c101 = d[b1, g0, r1]
                c011 = d[b1, g1, r0]; c111 = d[b1, g1, r1]
                c00 = c000 * (1-fr) + c100 * fr
                c10 = c010 * (1-fr) + c110 * fr
                c01 = c001 * (1-fr) + c101 * fr
                c11 = c011 * (1-fr) + c111 * fr
                c0 = c00 * (1-fg) + c10 * fg
                c1 = c01 * (1-fg) + c11 * fg
                out[y0:y1] = c0 * (1-fb) + c1 * fb
        out = np.clip(out, 0.0, 1.0)
        if t < 0.999:
            out = rgb * (1.0 - t) + out * t
        bgr = cv2.cvtColor((out * 255.0 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR)
        return bgr
