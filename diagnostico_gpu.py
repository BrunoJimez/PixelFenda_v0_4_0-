from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

REPORT = Path(__file__).with_name("diagnostico_pixelfenda_nvenc.txt")


def run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return p.returncode, p.stdout or ""
    except FileNotFoundError as exc:
        return 127, f"Arquivo/comando não encontrado: {exc}"
    except subprocess.TimeoutExpired as exc:
        data = exc.stdout or ""
        if isinstance(data, bytes):
            data = data.decode("utf-8", "replace")
        return 124, f"TIMEOUT\n{data}"
    except Exception as exc:
        return 125, f"{type(exc).__name__}: {exc}"


def candidate_ffmpegs() -> list[str]:
    found: list[str] = []

    env = os.environ.get("PIXELFENDA_FFMPEG")
    if env:
        found.append(env)

    system = shutil.which("ffmpeg")
    if system:
        found.append(system)

    try:
        import imageio_ffmpeg  # type: ignore
        found.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass

    # Locais comuns no Windows.
    for raw in (
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    ):
        if Path(raw).exists():
            found.append(raw)

    unique: list[str] = []
    seen = set()
    for item in found:
        key = os.path.normcase(os.path.abspath(item))
        if key not in seen and Path(item).exists():
            seen.add(key)
            unique.append(item)
    return unique


def section(title: str, body: str = "") -> str:
    bar = "=" * 78
    return f"\n{bar}\n{title}\n{bar}\n{body.rstrip()}\n"


def classify_nvenc_error(text: str) -> str:
    t = text.lower()
    if "unknown encoder" in t or "encoder not found" in t:
        return "FFmpeg sem esse encoder NVENC compilado/habilitado."
    if "cannot load nvcuda" in t or "cannot load nvencodeapi" in t or "nvencodeapi64.dll" in t:
        return "Biblioteca/driver NVIDIA NVENC não pôde ser carregado."
    if "minimum required nvidia driver" in t or "driver does not support the required nvenc api version" in t:
        return "Driver NVIDIA antigo/incompatível com a API NVENC exigida pelo FFmpeg."
    if "no capable devices found" in t or "no nvenc capable devices found" in t:
        return "FFmpeg não encontrou um dispositivo NVENC utilizável."
    if "openencode session" in t or "failed to open nvenc" in t or "initialize encoder" in t:
        return "O encoder existe, mas a inicialização do NVENC falhou em tempo de execução."
    if "permission" in t or "access is denied" in t:
        return "Falha de permissão/acesso ao dispositivo ou arquivo."
    return "Falha não classificada automaticamente; veja a saída completa abaixo."


def test_encoder(ffmpeg: str, codec: str) -> tuple[bool, str, str]:
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "verbose",
        "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30",
        "-t", "1",
        "-an",
        "-c:v", codec,
        "-preset", "p4",
        "-f", "null",
        "NUL" if os.name == "nt" else "/dev/null",
    ]
    code, output = run(cmd, timeout=30)
    return code == 0, classify_nvenc_error(output), output


def main() -> int:
    chunks: list[str] = []
    chunks.append("PixelFenda v0.2.1 — Diagnóstico NVENC aprofundado\n")
    chunks.append(f"Sistema: {platform.platform()}\nPython: {platform.python_version()}\n")
    chunks.append(f"Executável Python: {os.sys.executable}\n")

    # NVIDIA / driver
    smi = shutil.which("nvidia-smi")
    if smi:
        code, out = run([
            smi,
            "--query-gpu=name,driver_version,pci.bus_id,video_codec_utilization.encoder",
            "--format=csv,noheader"
        ])
        if code != 0:
            code, out = run([smi])
        chunks.append(section("NVIDIA / DRIVER (nvidia-smi)", out))
    else:
        chunks.append(section("NVIDIA / DRIVER", "nvidia-smi não encontrado no PATH."))

    # OpenGL
    try:
        from pixelfenda.gpu import create_gpu_pipeline
        g = create_gpu_pipeline(64, 64, 1337)
        text = f"OK\nRenderer: {g.renderer}"
        g.release()
    except Exception as exc:
        text = f"FALHA\n{type(exc).__name__}: {exc}"
    chunks.append(section("OPENGL / MODERNGL", text))

    candidates = candidate_ffmpegs()
    if not candidates:
        chunks.append(section("FFMPEG", "Nenhum FFmpeg encontrado."))
    else:
        chunks.append(section(
            "FFMPEG CANDIDATOS",
            "\n".join(f"{i+1}. {p}" for i, p in enumerate(candidates))
        ))

    any_nvenc = False

    for index, ffmpeg in enumerate(candidates, 1):
        code, version = run([ffmpeg, "-hide_banner", "-version"])
        chunks.append(section(f"FFMPEG #{index} — VERSÃO", f"Caminho: {ffmpeg}\n\n{version}"))

        code, encoders = run([ffmpeg, "-hide_banner", "-encoders"])
        nvenc_lines = [
            line for line in encoders.splitlines()
            if "nvenc" in line.lower()
        ]
        chunks.append(section(
            f"FFMPEG #{index} — ENCODERS NVENC LISTADOS",
            "\n".join(nvenc_lines) if nvenc_lines
            else "Nenhuma linha NVENC encontrada em `ffmpeg -encoders`."
        ))

        for codec in ("h264_nvenc", "hevc_nvenc", "av1_nvenc"):
            listed = any(codec.lower() in line.lower() for line in nvenc_lines)
            ok, diagnosis, details = test_encoder(ffmpeg, codec)
            any_nvenc |= ok
            status = "OK" if ok else "FALHA"
            diagnosis_text = "Encoder inicializado e encode concluído com sucesso." if ok else diagnosis
            summary = (
                f"Status: {status}\n"
                f"Listado pelo FFmpeg: {'SIM' if listed else 'NÃO'}\n"
                f"Diagnóstico: {diagnosis_text}\n\n"
                f"--- Saída completa do teste ---\n{details}"
            )
            chunks.append(section(f"FFMPEG #{index} — TESTE {codec}", summary))

    # Recomendações automáticas
    if any_nvenc:
        recommendation = (
            "Pelo menos um encoder NVENC funcionou.\n"
            "O PixelFenda pode usar NVENC; se o programa ainda cair para CPU, "
            "o próximo hotfix deve priorizar o FFmpeg que passou neste relatório."
        )
    else:
        recommendation = (
            "Nenhum encoder NVENC conseguiu concluir o teste.\n"
            "Verifique, nas seções acima, se os encoders estão LISTADOS.\n\n"
            "1) Se NÃO estiverem listados: o build do FFmpeg não possui NVENC; "
            "troque por um build Windows que inclua os encoders NVIDIA.\n"
            "2) Se estiverem listados mas falharem com mensagem de driver/API: "
            "atualize o driver NVIDIA Studio ou Game Ready.\n"
            "3) Se estiverem listados e o erro for outro, envie este relatório completo; "
            "ele contém a causa exata para o próximo hotfix."
        )
    chunks.append(section("CONCLUSÃO AUTOMÁTICA", recommendation))

    report = "".join(chunks)
    print(report)
    try:
        REPORT.write_text(report, encoding="utf-8")
        print(f"\nRelatório salvo em:\n{REPORT}")
    except Exception as exc:
        print(f"\nNão foi possível salvar o relatório: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
