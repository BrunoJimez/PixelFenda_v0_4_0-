from __future__ import annotations

import argparse
import json
from pathlib import Path

from pixelfenda.app import run_gui
from pixelfenda.engine import probe_video, render_video_layers
from pixelfenda.ffmpeg_utils import make_output_path
from pixelfenda.model import LayerSpec, ProjectDocument
from pixelfenda.presets import EFFECT_PRESETS, FILTER_PRESETS, RESOLUTION_BY_KEY
from pixelfenda.scene import analyze_scenes


def _resolve_size(doc: ProjectDocument, input_path: str) -> tuple[int, int]:
    p = RESOLUTION_BY_KEY.get(doc.resolution, RESOLUTION_BY_KEY["original"])
    if p.key == "original":
        info = probe_video(input_path)
        return info.width, info.height
    if p.key == "custom":
        return int(doc.width), int(doc.height)
    return int(p.width), int(p.height)


def main() -> None:
    p = argparse.ArgumentParser(description="PixelFenda v0.4.0 — Temporal Director")
    p.add_argument("--cli", action="store_true", help="Executa sem interface gráfica")
    p.add_argument("--project", help="Projeto .pixelfenda.json")
    p.add_argument("-i", "--input")
    p.add_argument("-o", "--output")
    p.add_argument("--resolution", default="original", choices=list(RESOLUTION_BY_KEY))
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--resize", default="crop", choices=["crop", "fit", "stretch"])
    p.add_argument("--effect", default="corrupted_memory", choices=list(EFFECT_PRESETS))
    p.add_argument("--effect-intensity", type=float, default=72)
    p.add_argument("--filter", default="none", choices=list(FILTER_PRESETS))
    p.add_argument("--filter-intensity", type=float, default=82)
    p.add_argument("--reactive", default="none", choices=["none", "motion", "audio", "both"])
    p.add_argument("--scene-mode", default="off", choices=["off", "pulse", "reset", "mutate"])
    p.add_argument("--scene-threshold", type=float, default=0.22)
    p.add_argument("--audio-mode", default="original", choices=["original", "silent", "replace", "mix", "vocals_only", "instrumental_only"])
    p.add_argument("--music")
    p.add_argument("--stem-vocals")
    p.add_argument("--stem-instrumental")
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--encoder", default="auto", choices=["auto", "cpu_h264", "h264_nvenc", "hevc_nvenc", "av1_nvenc"])
    p.add_argument("--gpu", default="auto", choices=["auto", "gpu", "cpu"])
    p.add_argument("--max-seconds", type=float)
    p.add_argument("--analyze-scenes", action="store_true")
    a = p.parse_args()
    if not a.cli and not a.analyze_scenes:
        run_gui()
        return

    if a.project:
        doc = ProjectDocument.load(a.project)
    else:
        layers = [LayerSpec(kind="effect", key=a.effect, intensity=max(0, min(100, a.effect_intensity))/100)]
        if a.filter != "none":
            layers.append(LayerSpec(kind="filter", key=a.filter, intensity=max(0, min(100, a.filter_intensity))/100))
        doc = ProjectDocument(
            input_path=a.input or "", output_path=a.output or "", resolution=a.resolution,
            width=a.width, height=a.height, resize_mode=a.resize, encoder_mode=a.encoder,
            gpu_mode=a.gpu, seed=a.seed, reactive_mode=a.reactive, scene_mode=a.scene_mode,
            scene_threshold=a.scene_threshold, audio_mode=a.audio_mode, music_path=a.music,
            stem_vocals_path=a.stem_vocals, stem_instrumental_path=a.stem_instrumental,
            layers=layers,
        )
    if a.input:
        doc.input_path = a.input
    if a.output:
        doc.output_path = a.output
    if not doc.input_path:
        p.error("--input é obrigatório no modo CLI (ou deve estar salvo no projeto)")

    if a.analyze_scenes:
        events = analyze_scenes(doc.input_path, threshold=doc.scene_threshold, max_seconds=a.max_seconds)
        print(json.dumps([e.__dict__ for e in events], ensure_ascii=False, indent=2))
        return

    w, h = _resolve_size(doc, doc.input_path)
    out = doc.output_path or make_output_path(doc.input_path, "v040")
    def prog(v, t):
        print(f"[{v*100:6.2f}%] {t}", flush=True)
    result = render_video_layers(
        doc.input_path, out, w, h, doc.layers,
        resize_mode=doc.resize_mode, seed=doc.seed, reactive_mode=doc.reactive_mode,
        scene_mode=doc.scene_mode, scene_threshold=doc.scene_threshold,
        audio_mode=doc.audio_mode, music_path=doc.music_path,
        stem_vocals_path=doc.stem_vocals_path, stem_instrumental_path=doc.stem_instrumental_path,
        encoder_mode=doc.encoder_mode, gpu_mode=doc.gpu_mode,
        max_seconds=a.max_seconds, progress=prog,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
