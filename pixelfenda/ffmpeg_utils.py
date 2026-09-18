from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


def find_ffmpeg() -> str:
    """Return the FFmpeg executable used by PixelFenda.

    Prefer the system executable when one is explicitly available on PATH. This is
    useful on Windows because full builds commonly expose newer NVENC support than
    the bundled imageio-ffmpeg binary. The bundled binary remains a fallback.
    """
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError(
            "FFmpeg não foi encontrado. Instale o FFmpeg ou execute: pip install imageio-ffmpeg"
        ) from exc


@lru_cache(maxsize=16)
def _encoder_works_cached(codec: str, ffmpeg: str) -> bool:
    """Perform a real encode smoke test at a NVENC-safe resolution.

    v0.2.0 tested hardware encoders with a 64x64 source. Some NVENC generations /
    codec combinations reject tiny frame sizes even when the encoder and GPU are
    perfectly functional, producing a false negative. The diagnostic supplied by
    the user demonstrated successful 1280x720 encodes for H.264, HEVC and AV1, so
    the application now validates encoders with a short 1280x720 test instead.
    """
    null_target = "NUL" if os.name == "nt" else "/dev/null"
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30",
        "-t", "0.35",
        "-an",
        "-c:v", codec,
        "-preset", "p4" if codec.endswith("_nvenc") else "medium",
        "-f", "null",
        null_target,
    ]
    try:
        r = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.returncode == 0
    except Exception:
        return False


def encoder_works(codec: str, ffmpeg: str | None = None) -> bool:
    ffmpeg = os.path.abspath(ffmpeg or find_ffmpeg())
    return _encoder_works_cached(codec, ffmpeg)


def nvenc_works(ffmpeg: str | None = None) -> bool:
    return encoder_works("h264_nvenc", ffmpeg)


def clear_encoder_probe_cache() -> None:
    """Useful after the user changes FFmpeg or GPU drivers while the app is open."""
    _encoder_works_cached.cache_clear()


def make_output_path(input_path: str, effect_key: str = "video", suffix: str = "") -> str:
    p = Path(input_path)
    tag = effect_key or "video"
    return str(p.with_name(f"{p.stem}_pixelfenda_{tag}{suffix}.mp4"))


def ensure_parent(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
