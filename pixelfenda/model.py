from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import uuid


@dataclass
class LayerSpec:
    """Serializable processing layer used by PixelFenda v0.3+.

    kind: effect | filter | lut
    intensity controls the effect/filter/LUT itself.
    opacity controls how the processed result is blended back into the stack.
    mod_source selects a per-layer modulation source.
    """

    kind: str = "effect"
    key: str = "corrupted_memory"
    intensity: float = 0.72
    opacity: float = 1.0
    blend: str = "normal"
    mod_source: str = "none"
    mod_amount: float = 0.0
    enabled: bool = True
    scene_reset: bool = False
    lut_path: str | None = None
    name: str | None = None
    # v0.4 temporal window + keyframes
    start_s: float = 0.0
    end_s: float = -1.0
    fade_in_s: float = 0.0
    fade_out_s: float = 0.0
    keyframe_ease: str = "smooth"
    keyframes: list[dict[str, float]] = field(default_factory=list)
    # v0.4 spatial mask + lightweight tracking
    mask_kind: str = "full"
    mask_x: float = 0.5
    mask_y: float = 0.5
    mask_w: float = 0.6
    mask_h: float = 0.6
    mask_feather: float = 0.08
    mask_angle: float = 0.0
    mask_invert: bool = False
    mask_track: bool = False
    mask_track_strength: float = 1.0
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def normalized(self) -> "LayerSpec":
        self.kind = self.kind if self.kind in {"effect", "filter", "lut"} else "effect"
        self.intensity = max(0.0, min(1.0, float(self.intensity)))
        self.opacity = max(0.0, min(1.0, float(self.opacity)))
        self.mod_amount = max(0.0, min(1.0, float(self.mod_amount)))
        self.enabled = bool(self.enabled)
        self.scene_reset = bool(self.scene_reset)
        self.start_s = max(0.0, float(self.start_s))
        self.end_s = float(self.end_s)
        self.fade_in_s = max(0.0, float(self.fade_in_s))
        self.fade_out_s = max(0.0, float(self.fade_out_s))
        self.keyframe_ease = self.keyframe_ease if self.keyframe_ease in {"linear","smooth","ease_in","ease_out","hold"} else "smooth"
        from .temporal import normalize_keyframes
        self.keyframes = normalize_keyframes(self.keyframes or [])
        self.mask_kind = self.mask_kind if self.mask_kind in {"full","rectangle","ellipse","linear","vignette"} else "full"
        self.mask_x = max(0.0, min(1.0, float(self.mask_x)))
        self.mask_y = max(0.0, min(1.0, float(self.mask_y)))
        self.mask_w = max(0.01, min(1.5, float(self.mask_w)))
        self.mask_h = max(0.01, min(1.5, float(self.mask_h)))
        self.mask_feather = max(0.0, min(1.0, float(self.mask_feather)))
        self.mask_angle = float(self.mask_angle)
        self.mask_invert = bool(self.mask_invert)
        self.mask_track = bool(self.mask_track)
        self.mask_track_strength = max(0.0, min(1.0, float(self.mask_track_strength)))
        return self

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LayerSpec":
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in allowed}).normalized()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProjectDocument:
    format_version: int = 4
    app_version: str = "0.4.0"
    name: str = "Projeto PixelFenda"
    input_path: str = ""
    output_path: str = ""
    resolution: str = "original"
    width: int = 1080
    height: int = 1920
    resize_mode: str = "crop"
    encoder_mode: str = "auto"
    gpu_mode: str = "auto"
    seed: int = 1337
    reactive_mode: str = "none"
    scene_mode: str = "off"
    scene_threshold: float = 0.22
    audio_mode: str = "original"
    music_path: str | None = None
    stem_vocals_path: str | None = None
    stem_instrumental_path: str | None = None
    layers: list[LayerSpec] = field(default_factory=lambda: [LayerSpec()])

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["layers"] = [x.to_dict() for x in self.layers]
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProjectDocument":
        kwargs = dict(raw)
        kwargs["layers"] = [LayerSpec.from_dict(x) for x in raw.get("layers", [])]
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in kwargs.items() if k in allowed})

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ProjectDocument":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Projeto PixelFenda inválido: raiz JSON deve ser um objeto.")
        return cls.from_dict(raw)


@dataclass
class RenderJob:
    input_path: str
    output_path: str
    label: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RenderJob":
        return cls(str(raw.get("input_path", "")), str(raw.get("output_path", "")), str(raw.get("label", "")))
