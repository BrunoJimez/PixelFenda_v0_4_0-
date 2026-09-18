from __future__ import annotations

from dataclasses import dataclass
import subprocess

import cv2
import numpy as np

from .ffmpeg_utils import find_ffmpeg


@dataclass
class ReactiveState:
    motion: float = 0.0
    motion_dx: float = 0.0
    motion_dy: float = 0.0
    audio: float = 0.0
    bass: float = 0.0
    mids: float = 0.0
    treble: float = 0.0
    beat: float = 0.0

    @property
    def combined(self) -> float:
        return float(np.clip(max(self.motion, self.audio, self.beat), 0.0, 1.0))


class MotionAnalyzer:
    """Low-resolution dense optical flow used only to drive effect parameters."""

    def __init__(self, width: int = 160, height: int = 90) -> None:
        self.width = width
        self.height = height
        self.prev: np.ndarray | None = None

    def update(self, frame_bgr: np.ndarray) -> tuple[float, float, float]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (self.width, self.height), interpolation=cv2.INTER_AREA)
        if self.prev is None:
            self.prev = gray
            return 0.0, 0.0, 0.0
        flow = cv2.calcOpticalFlowFarneback(
            self.prev, gray, None, 0.5, 2, 11, 2, 5, 1.1, 0
        )
        self.prev = gray
        fx, fy = flow[..., 0], flow[..., 1]
        mag = np.sqrt(fx * fx + fy * fy)
        # Robust statistic: moving subjects should count without one outlier dominating.
        p80 = float(np.percentile(mag, 80))
        strength = float(np.clip(p80 / 6.0, 0.0, 1.0))
        moving = mag > max(0.25, np.percentile(mag, 65))
        if np.any(moving):
            dx = float(np.clip(np.median(fx[moving]) / 8.0, -1.0, 1.0))
            dy = float(np.clip(np.median(fy[moving]) / 8.0, -1.0, 1.0))
        else:
            dx = dy = 0.0
        return strength, dx, dy


class AudioReactiveTrack:
    """Pre-computes frame-synchronous FFT features using only FFmpeg + NumPy."""

    def __init__(self, features: np.ndarray, loop: bool = False) -> None:
        self.features = features.astype(np.float32, copy=False)
        self.loop = bool(loop)

    @classmethod
    def silent(cls, frames: int) -> "AudioReactiveTrack":
        return cls(np.zeros((max(1, frames), 5), dtype=np.float32), loop=False)

    @classmethod
    def from_media(
        cls,
        path: str,
        fps: float,
        total_frames: int,
        sample_rate: int = 16000,
        loop: bool = False,
    ) -> "AudioReactiveTrack":
        if total_frames <= 0:
            return cls.silent(1)
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path,
            "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-",
        ]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        except Exception:
            return cls.silent(total_frames)
        if proc.returncode != 0 or not proc.stdout:
            return cls.silent(total_frames)
        samples = np.frombuffer(proc.stdout, dtype="<f4")
        if samples.size < 256:
            return cls.silent(total_frames)

        win = 1024
        hann = np.hanning(win).astype(np.float32)
        freqs = np.fft.rfftfreq(win, d=1.0 / sample_rate)
        feature_frames = total_frames
        if loop:
            source_frames = max(1, int(np.ceil((samples.size / sample_rate) * fps)))
            feature_frames = min(total_frames, source_frames)
        out = np.zeros((feature_frames, 5), dtype=np.float32)
        for i in range(feature_frames):
            center = int(round((i / fps) * sample_rate))
            start = center - win // 2
            seg = np.zeros(win, dtype=np.float32)
            s0 = max(0, start)
            s1 = min(samples.size, start + win)
            if s1 > s0:
                seg[(s0 - start):(s1 - start)] = samples[s0:s1]
            rms = float(np.sqrt(np.mean(seg * seg) + 1e-12))
            spec = np.abs(np.fft.rfft(seg * hann))
            bass = float(np.mean(spec[(freqs >= 35) & (freqs < 220)]))
            mids = float(np.mean(spec[(freqs >= 220) & (freqs < 2500)]))
            treble = float(np.mean(spec[(freqs >= 2500) & (freqs < 7500)]))
            out[i, :4] = (rms, bass, mids, treble)

        # Percentile normalization is resilient to one loud transient.
        for col in range(4):
            scale = float(np.percentile(out[:, col], 95))
            if scale > 1e-9:
                out[:, col] = np.clip(out[:, col] / scale, 0.0, 1.0)
        energy = out[:, 0]
        smooth = cv2.GaussianBlur(energy.reshape(-1, 1), (1, 0), sigmaX=0, sigmaY=2).reshape(-1)
        onset = np.maximum(0.0, energy - np.roll(smooth, 1))
        onset[0] = 0.0
        scale = float(np.percentile(onset, 95))
        if scale > 1e-9:
            onset = np.clip(onset / scale, 0.0, 1.0)
        out[:, 4] = onset
        return cls(out, loop=loop)

    def at(self, frame_index: int) -> tuple[float, float, float, float, float]:
        if self.features.size == 0:
            return 0.0, 0.0, 0.0, 0.0, 0.0
        i = int(frame_index % len(self.features)) if self.loop else int(np.clip(frame_index, 0, len(self.features) - 1))
        return tuple(float(x) for x in self.features[i])  # type: ignore[return-value]
