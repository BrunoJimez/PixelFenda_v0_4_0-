from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import numpy as np
import cv2

from .effects import CPUEffectEngine, PersistentVRAMEffect
from .filters import FilterEngine
from .gpu import GPU_EFFECT_IDS, FILTER_IDS, create_gpu_pipeline
from .lut import CubeLUT
from .model import LayerSpec
from .presets import VRAM_EFFECTS
from .reactive import ReactiveState
from .scene import SceneCutDetector
from .masks import MaskTracker, build_mask
from .temporal import temporal_values

BLEND_MODES = {
    "normal": "Normal",
    "screen": "Screen",
    "multiply": "Multiply",
    "add": "Add",
    "difference": "Difference",
    "overlay": "Overlay",
    "softlight": "Soft Light",
    "lighten": "Lighten",
    "darken": "Darken",
}
BLEND_BY_LABEL = {v: k for k, v in BLEND_MODES.items()}

MOD_SOURCES = {
    "none": "Sem modulação",
    "audio": "Energia do áudio",
    "bass": "Graves",
    "mids": "Médios",
    "treble": "Agudos",
    "beat": "Batida/transiente",
    "motion": "Movimento da cena",
    "scene": "Pulso de corte de cena",
    "lfo": "LFO lento",
}
MOD_BY_LABEL = {v: k for k, v in MOD_SOURCES.items()}

SCENE_MODES = {
    "off": "Desligado",
    "pulse": "Pulso nos cortes",
    "reset": "Resetar memória/feedback nos cortes",
    "mutate": "Auto Scene Mutator",
}
SCENE_BY_LABEL = {v: k for k, v in SCENE_MODES.items()}

GPU_FEEDBACK_EFFECTS = {"spectral_echo", "recursive_feedback"}


def blend_images(base: np.ndarray, layer: np.ndarray, mode: str, opacity: float) -> np.ndarray:
    a = float(np.clip(opacity, 0.0, 1.0))
    if a <= 0.0:
        return base
    if mode == "normal" and a >= 0.999:
        return layer
    b = base.astype(np.float32) / 255.0
    l = layer.astype(np.float32) / 255.0
    if mode == "screen":
        mixed = 1.0 - (1.0 - b) * (1.0 - l)
    elif mode == "multiply":
        mixed = b * l
    elif mode == "add":
        mixed = np.clip(b + l, 0.0, 1.0)
    elif mode == "difference":
        mixed = np.abs(b - l)
    elif mode == "overlay":
        mixed = np.where(b <= 0.5, 2.0 * b * l, 1.0 - 2.0 * (1.0 - b) * (1.0 - l))
    elif mode == "softlight":
        mixed = (1.0 - 2.0*l) * b*b + 2.0*l*b
    elif mode == "lighten":
        mixed = np.maximum(b, l)
    elif mode == "darken":
        mixed = np.minimum(b, l)
    else:
        mixed = l
    out = b * (1.0 - a) + mixed * a
    return np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)


def blend_images_masked(base: np.ndarray, layer: np.ndarray, mode: str, opacity: float, mask: np.ndarray | None) -> np.ndarray:
    if mask is None:
        return blend_images(base, layer, mode, opacity)
    a = np.clip(mask.astype(np.float32) * float(np.clip(opacity, 0.0, 1.0)), 0.0, 1.0)[..., None]
    if float(a.max()) <= 1e-6:
        return base
    mixed = blend_images(base, layer, mode, 1.0).astype(np.float32)
    b = base.astype(np.float32)
    return np.clip(b * (1.0 - a) + mixed * a + 0.5, 0, 255).astype(np.uint8)


def modulation_value(source: str, state: ReactiveState, scene_pulse: float, time_s: float, seed: int) -> float:
    if source == "audio": return state.audio
    if source == "bass": return state.bass
    if source == "mids": return state.mids
    if source == "treble": return state.treble
    if source == "beat": return state.beat
    if source == "motion": return state.motion
    if source == "scene": return scene_pulse
    if source == "lfo":
        phase = (seed % 997) / 997.0 * math.tau
        return 0.5 + 0.5 * math.sin(time_s * math.tau * 0.33 + phase)
    return 0.5


@dataclass
class _Runtime:
    spec: LayerSpec
    cpu: CPUEffectEngine | None = None
    filt: FilterEngine | None = None
    vram: PersistentVRAMEffect | None = None
    lut: CubeLUT | None = None
    prev_gpu: np.ndarray | None = None
    scene_gain: float = 1.0
    mask_tracker: MaskTracker | None = None


class LayerStackProcessor:
    """Stateful multi-layer compositor for PixelFenda v0.4.0 with temporal envelopes and masks."""

    def __init__(
        self,
        width: int,
        height: int,
        layers: list[LayerSpec],
        *,
        seed: int = 1337,
        gpu_mode: str = "auto",
        fps: float = 30.0,
        scene_mode: str = "off",
        scene_threshold: float = 0.22,
        duration: float = 0.0,
    ) -> None:
        self.width, self.height = int(width), int(height)
        self.layers = [LayerSpec.from_dict(x.to_dict()) for x in layers]
        self.seed = int(seed)
        self.fps = float(max(1.0, fps))
        self.gpu_mode = gpu_mode
        self.scene_mode = scene_mode
        self.scene_threshold = float(scene_threshold)
        self.duration = float(max(0.0, duration))
        self.rng = np.random.default_rng(seed)
        self.frame_index = 0
        self.scene_index = 0
        self.scene_detector = SceneCutDetector(threshold=scene_threshold, min_gap_frames=max(4, int(self.fps * 0.18)))
        self.gpu = None
        self.renderer = "CPU"
        if gpu_mode != "cpu":
            try:
                self.gpu = create_gpu_pipeline(self.width, self.height, self.seed)
                self.renderer = self.gpu.renderer
            except Exception as exc:
                if gpu_mode == "gpu":
                    raise RuntimeError(f"GPU/OpenGL solicitada, mas não pôde ser iniciada: {exc}") from exc
                self.gpu = None
                self.renderer = "CPU (fallback; GPU OpenGL indisponível)"
        self.runtimes = [self._build_runtime(i, spec) for i, spec in enumerate(self.layers)]

    def _build_runtime(self, idx: int, spec: LayerSpec) -> _Runtime:
        local_seed = self.seed + idx * 1009 + 17
        rt = _Runtime(spec=spec)
        if spec.kind == "effect":
            if spec.key in VRAM_EFFECTS:
                rt.vram = PersistentVRAMEffect(self.width, self.height, spec.intensity, local_seed, spec.key)
            else:
                rt.cpu = CPUEffectEngine(self.width, self.height, local_seed)
        elif spec.kind == "filter":
            rt.filt = FilterEngine(self.width, self.height, local_seed)
        elif spec.kind == "lut" and spec.lut_path:
            rt.lut = CubeLUT.load(spec.lut_path)
        if spec.mask_track and spec.mask_kind in {"rectangle", "ellipse"}:
            rt.mask_tracker = MaskTracker(self.width, self.height, spec)
        return rt

    def _reset_runtime(self, idx: int) -> None:
        old = self.runtimes[idx]
        self.runtimes[idx] = self._build_runtime(idx + self.scene_index * 97, old.spec)

    def _scene_event(self, frame: np.ndarray) -> tuple[bool, float]:
        if self.scene_mode == "off" and not any(x.spec.mod_source == "scene" or x.spec.scene_reset for x in self.runtimes):
            return False, 0.0
        cut, _score, pulse = self.scene_detector.update(frame)
        if cut:
            self.scene_index += 1
            if self.scene_mode in {"reset", "mutate"}:
                for i, rt in enumerate(self.runtimes):
                    if self.scene_mode == "reset" or rt.spec.scene_reset:
                        self._reset_runtime(i)
            if self.scene_mode == "mutate":
                for rt in self.runtimes:
                    if rt.spec.enabled:
                        if rt.spec.kind == "filter":
                            rt.scene_gain = float(self.rng.uniform(0.82, 1.15))
                        else:
                            rt.scene_gain = float(self.rng.uniform(0.62, 1.38))
        return cut, pulse

    def _strength(self, rt: _Runtime, state: ReactiveState, pulse: float, time_s: float, base_intensity: float, mod_amount: float) -> float:
        base = float(base_intensity)
        a = float(mod_amount)
        if a > 0.0 and rt.spec.mod_source != "none":
            v = modulation_value(rt.spec.mod_source, state, pulse, time_s, self.seed + self.frame_index)
            # Around the authored base value: 0 -> 57.5%, 0.5 -> 100%, 1 -> 142.5% at full amount.
            base *= 1.0 + a * 0.85 * (v - 0.5)
        if self.scene_mode == "pulse":
            base *= 1.0 + 0.35 * pulse
        base *= rt.scene_gain
        return float(np.clip(base, 0.0, 1.0))

    def process(self, frame_bgr: np.ndarray, state: ReactiveState) -> tuple[np.ndarray, dict]:
        self.frame_index += 1
        time_s = (self.frame_index - 1) / self.fps
        cut, pulse = self._scene_event(frame_bgr)
        out = frame_bgr
        active = 0
        masked = 0
        tracked = 0
        for idx, rt in enumerate(self.runtimes):
            spec = rt.spec
            if not spec.enabled:
                continue
            tv = temporal_values(spec, time_s, self.duration if self.duration > 0 else max(time_s + 1.0, 1.0))
            if not tv.active or tv.opacity <= 0.0:
                continue
            active += 1
            strength = self._strength(rt, state, pulse, time_s, tv.intensity, tv.mod_amount)
            base = out
            layer = base
            if spec.kind == "effect":
                if rt.vram is not None:
                    rt.vram.intensity = strength
                    layer = rt.vram.process(base, state)
                elif self.gpu is not None and spec.key in GPU_EFFECT_IDS:
                    if spec.key in GPU_FEEDBACK_EFFECTS:
                        if rt.prev_gpu is None:
                            rt.prev_gpu = np.zeros_like(base)
                        self.gpu.set_prev_frame(rt.prev_gpu)
                    layer = self.gpu.process(base, spec.key, "none", strength, state, self.fps, 0.0, time_seconds=time_s)
                    if spec.key in GPU_FEEDBACK_EFFECTS:
                        rt.prev_gpu = layer.copy()
                elif rt.cpu is not None:
                    layer = rt.cpu.process(base, spec.key, strength, state)
            elif spec.kind == "filter":
                if self.gpu is not None and spec.key in FILTER_IDS:
                    layer = self.gpu.process(base, "", spec.key, 0.0, state, self.fps, strength, time_seconds=time_s)
                elif rt.filt is not None:
                    layer = rt.filt.apply(base, spec.key, strength, self.frame_index)
            elif spec.kind == "lut" and rt.lut is not None:
                layer = rt.lut.apply(base, strength)
            center = None
            if rt.mask_tracker is not None:
                center = rt.mask_tracker.update(frame_bgr, spec)
                tracked += 1
            mask = None
            if spec.mask_kind != "full" or spec.mask_invert:
                mask = build_mask(self.width, self.height, spec, center_override=center)
                masked += 1
            out = blend_images_masked(base, layer, spec.blend, tv.opacity, mask)
        return out, {
            "active_layers": active,
            "masked_layers": masked,
            "tracked_masks": tracked,
            "scene_cut": cut,
            "scene_pulse": pulse,
            "scene_index": self.scene_index,
            "renderer": self.renderer,
        }

    def release(self) -> None:
        if self.gpu is not None:
            try:
                self.gpu.release()
            except Exception:
                pass
            self.gpu = None
