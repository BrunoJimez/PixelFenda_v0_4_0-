from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

from .effects import CPUEffectEngine, PersistentVRAMEffect
from .filters import FilterEngine
from .ffmpeg_utils import encoder_works, ensure_parent, find_ffmpeg
from .gpu import GPU_EFFECT_IDS, create_gpu_pipeline
from .presets import VRAM_EFFECTS
from .reactive import AudioReactiveTrack, MotionAnalyzer, ReactiveState

ProgressFn = Callable[[float, str], None]


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    frames: int
    duration: float


def probe_video(path: str) -> VideoInfo:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Não foi possível abrir o vídeo: {path}")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    duration = frames / fps if fps > 0 and frames > 0 else 0.0
    return VideoInfo(width, height, fps, frames, duration)


def fit_frame(frame: np.ndarray, width: int, height: int, mode: str) -> np.ndarray:
    src_h, src_w = frame.shape[:2]
    if mode == "stretch":
        return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    src_ratio, dst_ratio = src_w / src_h, width / height
    if mode == "crop":
        if src_ratio > dst_ratio:
            new_h, new_w = height, int(round(height * src_ratio))
        else:
            new_w, new_h = width, int(round(width / src_ratio))
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        x, y = max(0, (new_w-width)//2), max(0, (new_h-height)//2)
        return resized[y:y+height, x:x+width].copy()
    if src_ratio > dst_ratio:
        new_w, new_h = width, max(1, int(round(width/src_ratio)))
    else:
        new_h, new_w = height, max(1, int(round(height*src_ratio)))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((height, width, 3), np.uint8)
    x, y = (width-new_w)//2, (height-new_h)//2
    canvas[y:y+new_h, x:x+new_w] = resized
    return canvas


def _encoder_args(mode: str, ffmpeg: str) -> tuple[str, list[str]]:
    if mode == "auto":
        if encoder_works("h264_nvenc", ffmpeg):
            return "h264_nvenc", ["-c:v","h264_nvenc","-preset","p5","-cq","19","-b:v","0"]
        return "libx264", ["-c:v","libx264","-preset","medium","-crf","18"]
    if mode == "cpu_h264":
        return "libx264", ["-c:v","libx264","-preset","medium","-crf","18"]
    if mode in {"h264_nvenc","hevc_nvenc","av1_nvenc"}:
        if not encoder_works(mode, ffmpeg):
            raise RuntimeError(f"O encoder {mode} foi solicitado, mas não está disponível neste FFmpeg/GPU.")
        cq = "19" if mode == "h264_nvenc" else ("21" if mode == "hevc_nvenc" else "25")
        return mode, ["-c:v",mode,"-preset","p5","-cq",cq,"-b:v","0"]
    raise ValueError(f"Encoder desconhecido: {mode}")


def _audio_inputs_and_maps(input_path: str, audio_mode: str, music_path: str | None) -> tuple[list[str], list[str]]:
    if audio_mode == "silent":
        return [], ["-map","0:v:0","-an"]
    if audio_mode == "original":
        return ["-i",input_path], ["-map","0:v:0","-map","1:a?","-c:a","aac","-b:a","192k","-shortest"]
    if audio_mode in {"replace","mix"}:
        if not music_path or not os.path.isfile(music_path):
            raise ValueError("Selecione um arquivo de música/áudio válido para este modo de áudio.")
        if audio_mode == "replace":
            return ["-stream_loop","-1","-i",music_path], ["-map","0:v:0","-map","1:a:0","-c:a","aac","-b:a","192k","-shortest"]
        return ["-i",input_path,"-stream_loop","-1","-i",music_path], [
            "-filter_complex","[2:a]volume=0.65[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map","0:v:0","-map","[a]","-c:a","aac","-b:a","192k","-shortest",
        ]
    raise ValueError(f"Modo de áudio desconhecido: {audio_mode}")


def _build_gpu(width: int, height: int, seed: int, gpu_mode: str):
    if gpu_mode == "cpu":
        return None, "CPU"
    try:
        gpu = create_gpu_pipeline(width, height, seed)
        return gpu, gpu.renderer
    except Exception as exc:
        if gpu_mode == "gpu":
            raise RuntimeError(
                "GPU/OpenGL foi solicitada, mas o contexto não pôde ser criado. "
                "Instale moderngl + glcontext e atualize o driver NVIDIA Studio/Game Ready. "
                f"Detalhe: {exc}"
            ) from exc
        return None, "CPU (fallback; GPU OpenGL indisponível)"


def preview_process(
    frame_bgr: np.ndarray,
    width: int,
    height: int,
    *,
    resize_mode: str = "crop",
    apply_effect: bool = True,
    effect_preset: str = "corrupted_memory",
    effect_intensity: float = 0.72,
    apply_filter: bool = False,
    filter_preset: str = "none",
    filter_intensity: float = 1.0,
    seed: int = 1337,
    gpu_mode: str = "auto",
) -> tuple[np.ndarray, str]:
    frame = fit_frame(frame_bgr, width, height, resize_mode)
    r = ReactiveState(audio=0.35, bass=0.45, mids=0.35, treble=0.25, beat=0.25, motion=0.35, motion_dx=0.2)
    gpu, renderer = _build_gpu(width,height,seed,gpu_mode)
    filt = FilterEngine(width,height,seed)
    cpu = CPUEffectEngine(width,height,seed)
    out = frame
    try:
        if apply_effect and effect_preset in VRAM_EFFECTS:
            v = PersistentVRAMEffect(width,height,effect_intensity,seed,effect_preset)
            for _ in range(4): out = v.process(frame,r)
            if apply_filter:
                if gpu: out = gpu.process(out,"",filter_preset,0.0,r,30.0,filter_intensity)
                else: out = filt.apply(out,filter_preset,filter_intensity,4)
        elif gpu and ((apply_effect and effect_preset in GPU_EFFECT_IDS) or apply_filter):
            eff = effect_preset if apply_effect and effect_preset in GPU_EFFECT_IDS else ""
            fil = filter_preset if apply_filter else "none"
            for _ in range(2): out = gpu.process(out if _ else frame,eff,fil,effect_intensity if apply_effect else 0.0,r,30.0,filter_intensity if apply_filter else 0.0)
        else:
            if apply_effect: out = cpu.process(out,effect_preset,effect_intensity,r)
            if apply_filter: out = filt.apply(out,filter_preset,filter_intensity,1)
        return out, renderer
    finally:
        if gpu:
            gpu.release()


def render_video(
    input_path: str,
    output_path: str,
    width: int,
    height: int,
    *,
    resize_mode: str = "crop",
    apply_effect: bool = True,
    effect_preset: str = "corrupted_memory",
    effect_intensity: float = 0.72,
    apply_filter: bool = False,
    filter_preset: str = "none",
    filter_intensity: float = 1.0,
    seed: int = 1337,
    reactive_mode: str = "none",
    audio_mode: str = "original",
    music_path: str | None = None,
    encoder_mode: str = "auto",
    gpu_mode: str = "auto",
    max_seconds: float | None = None,
    progress: ProgressFn | None = None,
) -> dict:
    ensure_parent(output_path)
    info = probe_video(input_path)
    fps = info.fps if info.fps > 0 else 30.0
    total_frames = info.frames
    if max_seconds and max_seconds > 0:
        cap_frames = int(round(max_seconds*fps))
        total_frames = min(total_frames,cap_frames) if total_frames else cap_frames
    if not apply_effect and not apply_filter and progress:
        progress(0.01,"Conversão sem efeitos/filtros; preservando somente formato/áudio")

    ffmpeg=find_ffmpeg()
    encoder, codec_args = _encoder_args(encoder_mode,ffmpeg)
    audio_inputs,audio_maps = _audio_inputs_and_maps(input_path,audio_mode,music_path)

    cmd=[ffmpeg,"-hide_banner","-loglevel","error","-y","-f","rawvideo","-pix_fmt","bgr24","-s",f"{width}x{height}","-r",f"{fps:.8f}","-i","-"]
    cmd += audio_inputs
    cmd += audio_maps[:2] if audio_mode == "silent" else []
    cmd += codec_args + ["-pix_fmt","yuv420p"]
    if audio_mode != "silent": cmd += audio_maps
    elif "-an" not in cmd: cmd += ["-an"]
    cmd += ["-movflags","+faststart",output_path]

    # Reactive analysis is independent of what gets muxed into the final file.
    audio_track = AudioReactiveTrack.silent(max(1,total_frames))
    if reactive_mode in {"audio","both"}:
        source = music_path if music_path and os.path.isfile(music_path) else input_path
        if progress: progress(0.015,"Analisando música/áudio (FFT)")
        audio_track = AudioReactiveTrack.from_media(source,fps,max(1,total_frames),loop=bool(music_path and source==music_path))
    motion_an = MotionAnalyzer() if reactive_mode in {"motion","both"} else None

    gpu, gpu_renderer = _build_gpu(width,height,seed,gpu_mode)
    cpu = CPUEffectEngine(width,height,seed)
    vram = PersistentVRAMEffect(width,height,effect_intensity,seed,effect_preset) if apply_effect and effect_preset in VRAM_EFFECTS else None
    filt = FilterEngine(width,height,seed)

    cap=cv2.VideoCapture(input_path)
    if not cap.isOpened():
        if gpu: gpu.release()
        raise RuntimeError(f"Não foi possível abrir o vídeo: {input_path}")
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    rendered=0
    try:
        while True:
            if total_frames and rendered>=total_frames: break
            ok,frame=cap.read()
            if not ok: break
            fitted=fit_frame(frame,width,height,resize_mode)
            state=ReactiveState()
            if motion_an:
                state.motion,state.motion_dx,state.motion_dy=motion_an.update(fitted)
            if reactive_mode in {"audio","both"}:
                state.audio,state.bass,state.mids,state.treble,state.beat=audio_track.at(rendered)

            out=fitted
            if apply_effect and vram:
                out=vram.process(out,state)
                if apply_filter:
                    if gpu: out=gpu.process(out,"",filter_preset,0.0,state,fps,filter_intensity)
                    else: out=filt.apply(out,filter_preset,filter_intensity,rendered)
            elif gpu and ((apply_effect and effect_preset in GPU_EFFECT_IDS) or apply_filter):
                eff=effect_preset if apply_effect and effect_preset in GPU_EFFECT_IDS else ""
                fil=filter_preset if apply_filter else "none"
                # intensity controls effect; filter has its own blend only in CPU. In GPU,
                # pre-blend filter by running full grade then final user blend below when needed.
                out=gpu.process(out,eff,fil,effect_intensity if apply_effect else 0.0,state,fps,filter_intensity if apply_filter else 0.0)
            else:
                if apply_effect: out=cpu.process(out,effect_preset,effect_intensity,state)
                if apply_filter: out=filt.apply(out,filter_preset,filter_intensity,rendered)

            assert proc.stdin is not None
            proc.stdin.write(out.tobytes())
            rendered+=1
            if progress and (rendered==1 or rendered%5==0):
                denom=total_frames or max(1,rendered)
                progress(min(0.995,rendered/denom),f"Quadro {rendered}/{total_frames or '?'} | {gpu_renderer} | {encoder}")
    except BrokenPipeError:
        pass
    finally:
        cap.release()
        if gpu: gpu.release()
        if proc.stdin:
            try: proc.stdin.close()
            except Exception: pass
    stderr=proc.stderr.read() if proc.stderr else b""
    code=proc.wait()
    if code!=0:
        msg=stderr.decode("utf-8",errors="replace")[-5000:]
        raise RuntimeError(f"FFmpeg encerrou com erro ({code}).\n{msg}")
    if progress: progress(1.0,"Concluído")
    return {
        "input":input_path,"output":output_path,"width":width,"height":height,"fps":fps,
        "frames":rendered,"encoder":encoder,"gpu_renderer":gpu_renderer,
        "effect_enabled":apply_effect,"effect":effect_preset if apply_effect else None,"effect_intensity":effect_intensity,
        "filter_enabled":apply_filter,"filter":filter_preset if apply_filter else None,"filter_intensity":filter_intensity,
        "reactive":reactive_mode,"audio_mode":audio_mode,"music":music_path,"seed":seed,
    }

# ---------------------------------------------------------------------------
# PixelFenda v0.4.0 — Temporal Layer Stack renderer
# ---------------------------------------------------------------------------

from .layering import LayerStackProcessor
from .model import LayerSpec


def preview_layers(
    frame_bgr: np.ndarray,
    width: int,
    height: int,
    layers: list[LayerSpec],
    *,
    resize_mode: str = "crop",
    seed: int = 1337,
    gpu_mode: str = "auto",
    scene_mode: str = "off",
    scene_threshold: float = 0.22,
    time_s: float = 0.0,
    duration: float = 0.0,
) -> tuple[np.ndarray, str, dict]:
    frame = fit_frame(frame_bgr, width, height, resize_mode)
    state = ReactiveState(
        audio=0.42, bass=0.55, mids=0.38, treble=0.31, beat=0.34,
        motion=0.40, motion_dx=0.18, motion_dy=-0.06,
    )
    proc = LayerStackProcessor(
        width, height, layers, seed=seed, gpu_mode=gpu_mode, fps=30.0,
        scene_mode=scene_mode, scene_threshold=scene_threshold, duration=duration,
    )
    proc.frame_index = max(0, int(round(max(0.0, time_s) * 30.0)) - 3)
    meta: dict = {}
    out = frame
    try:
        # Warm temporal memories so feedback/VRAM layers are visible in preview.
        for _ in range(3):
            out, meta = proc.process(frame, state)
        return out, proc.renderer, meta
    finally:
        proc.release()


def _audio_inputs_and_maps_v3(
    input_path: str,
    audio_mode: str,
    music_path: str | None,
    stem_vocals_path: str | None,
    stem_instrumental_path: str | None,
) -> tuple[list[str], list[str]]:
    if audio_mode in {"original", "silent", "replace", "mix"}:
        return _audio_inputs_and_maps(input_path, audio_mode, music_path)
    if audio_mode == "vocals_only":
        source = stem_vocals_path
        label = "stem de voz"
    elif audio_mode == "instrumental_only":
        source = stem_instrumental_path
        label = "stem instrumental"
    else:
        raise ValueError(f"Modo de áudio desconhecido: {audio_mode}")
    if not source or not os.path.isfile(source):
        raise ValueError(
            f"O modo {audio_mode} exige um {label} válido. Execute a separação Demucs na aba Áudio/Ferramentas primeiro."
        )
    return ["-i", source], ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-shortest"]


def render_video_layers(
    input_path: str,
    output_path: str,
    width: int,
    height: int,
    layers: list[LayerSpec],
    *,
    resize_mode: str = "crop",
    seed: int = 1337,
    reactive_mode: str = "none",
    scene_mode: str = "off",
    scene_threshold: float = 0.22,
    audio_mode: str = "original",
    music_path: str | None = None,
    stem_vocals_path: str | None = None,
    stem_instrumental_path: str | None = None,
    encoder_mode: str = "auto",
    gpu_mode: str = "auto",
    max_seconds: float | None = None,
    progress: ProgressFn | None = None,
) -> dict:
    ensure_parent(output_path)
    info = probe_video(input_path)
    fps = info.fps if info.fps > 0 else 30.0
    total_frames = info.frames
    if max_seconds and max_seconds > 0:
        cap_frames = int(round(max_seconds * fps))
        total_frames = min(total_frames, cap_frames) if total_frames else cap_frames

    enabled_layers = [x for x in layers if x.enabled]
    if not enabled_layers and progress:
        progress(0.01, "Pilha vazia: conversão de formato/áudio sem mutação visual")

    ffmpeg = find_ffmpeg()
    encoder, codec_args = _encoder_args(encoder_mode, ffmpeg)
    audio_inputs, audio_maps = _audio_inputs_and_maps_v3(
        input_path, audio_mode, music_path, stem_vocals_path, stem_instrumental_path
    )
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
        "-r", f"{fps:.8f}", "-i", "-",
    ]
    cmd += audio_inputs
    cmd += audio_maps[:2] if audio_mode == "silent" else []
    cmd += codec_args + ["-pix_fmt", "yuv420p"]
    if audio_mode != "silent":
        cmd += audio_maps
    elif "-an" not in cmd:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", output_path]

    mods = {x.mod_source for x in enabled_layers}
    audio_mods = {"audio", "bass", "mids", "treble", "beat"}
    need_audio = reactive_mode in {"audio", "both"} or bool(mods & audio_mods)
    need_motion = reactive_mode in {"motion", "both"} or "motion" in mods

    audio_track = AudioReactiveTrack.silent(max(1, total_frames))
    if need_audio:
        if music_path and os.path.isfile(music_path):
            source = music_path
            loop = True
        elif audio_mode == "vocals_only" and stem_vocals_path and os.path.isfile(stem_vocals_path):
            source, loop = stem_vocals_path, False
        elif audio_mode == "instrumental_only" and stem_instrumental_path and os.path.isfile(stem_instrumental_path):
            source, loop = stem_instrumental_path, False
        else:
            source, loop = input_path, False
        if progress:
            progress(0.012, "Analisando áudio para modulação (FFT)")
        audio_track = AudioReactiveTrack.from_media(source, fps, max(1, total_frames), loop=loop)
    motion_an = MotionAnalyzer() if need_motion else None

    stack = LayerStackProcessor(
        width, height, layers, seed=seed, gpu_mode=gpu_mode, fps=fps,
        scene_mode=scene_mode, scene_threshold=scene_threshold,
        duration=(total_frames / fps if total_frames else info.duration),
    )
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        stack.release()
        raise RuntimeError(f"Não foi possível abrir o vídeo: {input_path}")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    rendered = 0
    last_meta: dict = {}
    try:
        while True:
            if total_frames and rendered >= total_frames:
                break
            ok, frame = cap.read()
            if not ok:
                break
            fitted = fit_frame(frame, width, height, resize_mode)
            state = ReactiveState()
            if motion_an is not None:
                state.motion, state.motion_dx, state.motion_dy = motion_an.update(fitted)
            if need_audio:
                state.audio, state.bass, state.mids, state.treble, state.beat = audio_track.at(rendered)
            out, last_meta = stack.process(fitted, state)
            assert proc.stdin is not None
            proc.stdin.write(out.tobytes())
            rendered += 1
            if progress and (rendered == 1 or rendered % 5 == 0):
                denom = total_frames or max(1, rendered)
                progress(
                    min(0.995, rendered / denom),
                    f"Quadro {rendered}/{total_frames or '?'} | {stack.renderer} | {encoder} | "
                    f"{last_meta.get('active_layers', 0)} camadas | {last_meta.get('masked_layers', 0)} máscaras | cena {last_meta.get('scene_index', 0)+1}",
                )
    except BrokenPipeError:
        pass
    finally:
        cap.release()
        stack.release()
        if proc.stdin:
            try:
                proc.stdin.close()
            except Exception:
                pass
    stderr = proc.stderr.read() if proc.stderr else b""
    code = proc.wait()
    if code != 0:
        msg = stderr.decode("utf-8", errors="replace")[-6000:]
        raise RuntimeError(f"FFmpeg encerrou com erro ({code}).\n{msg}")
    if progress:
        progress(1.0, "Concluído")
    return {
        "input": input_path,
        "output": output_path,
        "width": width,
        "height": height,
        "fps": fps,
        "frames": rendered,
        "encoder": encoder,
        "gpu_renderer": stack.renderer,
        "layers": [x.to_dict() for x in layers],
        "active_layers": len(enabled_layers),
        "reactive": reactive_mode,
        "scene_mode": scene_mode,
        "scenes_seen": int(last_meta.get("scene_index", 0)) + 1 if rendered else 0,
        "audio_mode": audio_mode,
        "music": music_path,
        "seed": seed,
    }
