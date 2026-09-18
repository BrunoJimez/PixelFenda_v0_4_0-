from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from pixelfenda.engine import preview_process
from pixelfenda.ffmpeg_utils import encoder_works, find_ffmpeg

ROOT = Path(__file__).resolve().parent


def make_test_frame(w: int = 640, h: int = 360) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    b = ((xx / max(1, w - 1)) * 255).astype(np.uint8)
    g = ((yy / max(1, h - 1)) * 255).astype(np.uint8)
    r = (((np.sin(xx / 27.0) + 1.0) * 0.5) * 255).astype(np.uint8)
    frame = np.dstack([b, g, r])
    cv2.rectangle(frame, (40, 45), (235, 235), (20, 20, 20), -1)
    cv2.putText(frame, "PIXELFENDA", (60, 125), cv2.FONT_HERSHEY_SIMPLEX, 1.15, (240, 240, 240), 2, cv2.LINE_AA)
    cv2.putText(frame, "v0.2.1 GPU TEST", (60, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (190, 210, 235), 1, cv2.LINE_AA)
    return frame


def preview_case(name: str, **kwargs) -> None:
    frame = make_test_frame()
    out, renderer = preview_process(frame, 640, 360, gpu_mode="auto", seed=1337, **kwargs)
    path = ROOT / f"_teste_v021_{name}.jpg"
    if not cv2.imwrite(str(path), out):
        raise RuntimeError(f"Não foi possível salvar {path}")
    print(f"[OK] {name}: {renderer}")
    print(f"     imagem: {path}")


def main() -> int:
    print("PixelFenda v0.2.1 — autoteste do hotfix\n")

    # Exact route that failed in the user's screenshots: CPU/VRAM effect followed
    # by a GPU filter when OpenGL is available.
    preview_case(
        "vram_mais_filtro",
        apply_effect=True,
        effect_preset="corrupted_memory",
        effect_intensity=0.744,
        apply_filter=True,
        filter_preset="vintage_70",
        filter_intensity=0.82,
    )

    # GPU effect + GPU filter in a single shader pass.
    preview_case(
        "shader_mais_filtro",
        apply_effect=True,
        effect_preset="digital_rain",
        effect_intensity=0.74,
        apply_filter=True,
        filter_preset="cold_archive",
        filter_intensity=0.82,
    )

    ffmpeg = find_ffmpeg()
    print(f"\nFFmpeg: {ffmpeg}")
    for codec in ("h264_nvenc", "hevc_nvenc", "av1_nvenc"):
        print(f"{codec}: {'OK' if encoder_works(codec, ffmpeg) else 'indisponível'}")

    print("\nAUTOTESTE CONCLUÍDO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
