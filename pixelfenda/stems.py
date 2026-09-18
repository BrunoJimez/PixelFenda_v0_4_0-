from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

ProgressFn = Callable[[float, str], None]


def demucs_python() -> str:
    configured = os.environ.get("PIXELFENDA_DEMUCS_PYTHON", "").strip()
    if configured and Path(configured).is_file():
        return configured
    root = Path(__file__).resolve().parent.parent
    candidates = [
        root / ".venv_demucs" / "Scripts" / "python.exe",
        root / ".venv_demucs" / "bin" / "python",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return sys.executable


def demucs_available(python_exe: str | None = None) -> bool:
    py = python_exe or demucs_python()
    try:
        r = subprocess.run(
            [py, "-c", "import demucs,sys; print(getattr(demucs,'__version__','ok'))"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.returncode == 0
    except Exception:
        return False


def separate_vocals(
    media_path: str,
    output_dir: str,
    *,
    device: str = "auto",
    model: str = "htdemucs",
    progress: ProgressFn | None = None,
) -> dict[str, str]:
    py = demucs_python()
    if not demucs_available(py):
        raise RuntimeError(
            "Demucs não está instalado no ambiente opcional. Use install_demucs_optional.bat "
            "ou configure PIXELFENDA_DEMUCS_PYTHON para um Python que tenha Demucs."
        )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dev_args: list[str] = [] if device == "auto" else ["-d", device]
    cmd = [py, "-m", "demucs", "--two-stems=vocals", "-n", model, "-o", str(out), *dev_args, media_path]
    if progress:
        progress(0.02, "Separando voz e instrumental com Demucs…")
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0:
        raise RuntimeError("Demucs encerrou com erro:\n" + (proc.stdout or "")[-6000:])
    stem = Path(media_path).stem
    bases = list(out.glob(f"*/{stem}"))
    if not bases:
        bases = [p for p in out.rglob(stem) if p.is_dir()]
    if not bases:
        raise RuntimeError("Demucs terminou, mas a pasta de stems não foi localizada.")
    base = bases[0]
    vocals = base / "vocals.wav"
    instrumental = base / "no_vocals.wav"
    if not vocals.is_file() or not instrumental.is_file():
        raise RuntimeError(f"Stems esperados não encontrados em {base}")
    if progress:
        progress(1.0, "Separação concluída")
    return {"vocals": str(vocals), "instrumental": str(instrumental), "folder": str(base)}
