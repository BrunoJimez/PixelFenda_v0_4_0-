from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolutionPreset:
    key: str
    label: str
    width: int | None
    height: int | None


RESOLUTION_PRESETS = [
    ResolutionPreset("original", "Tamanho original do vídeo", None, None),
    ResolutionPreset("tiktok", "TikTok / Shorts / Reels — 9:16 (1080×1920)", 1080, 1920),
    ResolutionPreset("youtube", "YouTube — 16:9 Full HD (1920×1080)", 1920, 1080),
    ResolutionPreset("instagram_reels", "Instagram Reels/Stories — 9:16 (1080×1920)", 1080, 1920),
    ResolutionPreset("instagram_square", "Instagram Feed — 1:1 (1080×1080)", 1080, 1080),
    ResolutionPreset("instagram_portrait", "Instagram Feed retrato — 4:5 (1080×1350)", 1080, 1350),
    ResolutionPreset("instagram_16_9", "Instagram / vídeo horizontal — 16:9 (1920×1080)", 1920, 1080),
    ResolutionPreset("instagram_landscape", "Instagram Feed paisagem — 1.91:1 (1080×566)", 1080, 566),
    ResolutionPreset("custom", "Resolução personalizada", None, None),
]
RESOLUTION_BY_KEY = {p.key: p for p in RESOLUTION_PRESETS}
RESOLUTION_BY_LABEL = {p.label: p for p in RESOLUTION_PRESETS}


# Os seis primeiros são preservados da v0.1.0. Os demais foram derivados das
# referências enviadas pelo usuário e de famílias clássicas de glitch/video art.
EFFECT_PRESETS = {
    "corrupted_memory": "VRAM Corrupted Memory — clássico v0.1",
    "tile_storm": "VRAM Tile Storm — blocos e páginas de textura",
    "palette_collapse": "VRAM Palette Collapse — bitplanes/paleta",
    "address_shift": "VRAM Address Shift — stride/tearing",
    "controlled": "VRAM Controlled Glitch — legível",
    "full_corruption": "VRAM Full Corruption — caos máximo",
    "ascii_terminal": "ASCII Terminal — raster/terminal 90s",
    "digital_rain": "Digital Rain — chuva de código verde",
    "gothic_crimson": "Gothic Crimson — trevas, aço e carmim",
    "spectral_echo": "Spectral Echo — rastros e persistência",
    "pixel_sort": "Pixel Sort — derretimento por luminância",
    "scanline_melt": "Scanline Melt — linhas deslocadas/slit-scan",
    "chromatic_vhs": "Chromatic VHS — fita, RGB split e jitter",
    "crt_terminal": "CRT Terminal — fósforo, scanlines e curvatura",
    "void_bloom": "Void Bloom — silhueta + halo luminoso",
    "neon_noir": "Neon Noir — noite elétrica e bordas luminosas",
    "retro_space": "Retro Space PC — sci-fi 90s / dithering",
    "datamosh_flow": "Datamosh Flow — macroblocos guiados por movimento",
    "recursive_feedback": "Recursive Feedback — eco recursivo de vídeo",
    "brutalist_collage": "Brutalist Collage — recortes, zooms e arquitetura",
    "cyber_wire": "Cyber Wire — wireframe ciano/magenta",
    "liquid_chrome": "Liquid Chrome — metal líquido digital",
    "psx_dither": "PSX Dither — 15-bit, pixels e dithering",
    "gothic_halo": "Gothic Halo — silhueta, halo e carmim",
    "signal_grid": "Signal Grid — grade de sinal e blocos",
    "temporal_shred": "Temporal Shred — tiras de memória temporal",
    "prism_rift": "Prism Rift — fratura RGB radial",
    "edge_strobe": "Edge Strobe — bordas pulsadas por beat/agudos",
    "data_bloom": "Data Bloom — bloom digital e blocos luminosos",
    "motion_tunnel": "Motion Tunnel — túnel de feedback e movimento",
}
EFFECT_BY_LABEL = {v: k for k, v in EFFECT_PRESETS.items()}
VRAM_EFFECTS = {
    "corrupted_memory", "tile_storm", "palette_collapse", "address_shift", "controlled", "full_corruption"
}
GPU_EFFECTS = {
    "ascii_terminal", "digital_rain", "gothic_crimson", "spectral_echo", "scanline_melt",
    "chromatic_vhs", "crt_terminal", "void_bloom", "neon_noir", "retro_space", "recursive_feedback",
    "cyber_wire", "liquid_chrome", "psx_dither", "gothic_halo", "signal_grid"
}

FILTER_PRESETS = {
    "none": "Sem filtro",
    "vintage_70": "Vintage 70 — quente, desbotado e granulado",
    "vintage_90": "Vintage 90 — verde/magenta e fita fotográfica",
    "cinematic_teal_amber": "Cinematic — teal & amber",
    "cold_archive": "Cold Archive — filme antigo frio",
    "silver_gray": "Silver Gray — cinza cinematográfico",
    "noir": "Noir — P&B de alto contraste",
    "odyssey_70": "Odisseia 70 — inspirado em 65/70mm fotoquímico",
    "bleach_bypass": "Bleach Bypass — prata, contraste e baixa saturação",
    "matrix_green": "Terminal Green — verde digital",
    "gothic_iron": "Gothic Iron — aço frio e vermelho profundo",
    "y2k_chrome": "Y2K Chrome — branco, prata e ciano",
    "dream_white": "Dream White — high-key etéreo",
    "neon_night": "Neon Night — azul/ciano noturno",
    "space_blue": "Space Blue — sci-fi PC 90s",
    "antique_sepia": "Antique Sepia — película envelhecida",
    "social_cool": "Social Cool — contraste frio moderno",
    "muted_linen": "Muted Linen — fosco e pouco saturado",
    "soft_bw": "Soft B&W — preto e branco suave",
    "infrared_ice": "Infrared Ice — negativo frio/ultravioleta",
}
FILTER_BY_LABEL = {v: k for k, v in FILTER_PRESETS.items()}

RESIZE_MODES = {
    "crop": "Preencher e recortar (crop)",
    "fit": "Encaixar com barras pretas (fit)",
    "stretch": "Esticar para a resolução",
}
RESIZE_BY_LABEL = {v: k for k, v in RESIZE_MODES.items()}

ENCODER_MODES = {
    "auto": "Automático — H.264 NVENC se disponível",
    "cpu_h264": "CPU — H.264 libx264",
    "h264_nvenc": "NVIDIA NVENC — H.264",
    "hevc_nvenc": "NVIDIA NVENC — H.265/HEVC",
    "av1_nvenc": "NVIDIA NVENC — AV1 (RTX 40+)",
}
ENCODER_BY_LABEL = {v: k for k, v in ENCODER_MODES.items()}

GPU_MODES = {
    "auto": "Automático — GPU OpenGL se disponível",
    "gpu": "Forçar GPU — OpenGL/RTX",
    "cpu": "Forçar CPU",
}
GPU_BY_LABEL = {v: k for k, v in GPU_MODES.items()}

REACTIVE_MODES = {
    "none": "Livre / não reativo",
    "motion": "Reagir ao movimento da cena",
    "audio": "Reagir à música/áudio",
    "both": "Movimento + música/áudio",
}
REACTIVE_BY_LABEL = {v: k for k, v in REACTIVE_MODES.items()}

AUDIO_MODES = {
    "original": "Manter áudio original",
    "silent": "Vídeo sem áudio",
    "replace": "Substituir por outra música/áudio",
    "mix": "Misturar áudio original + nova música",
    "vocals_only": "Somente voz — stem Demucs opcional",
    "instrumental_only": "Sem voz / instrumental — stem Demucs opcional",
}
AUDIO_BY_LABEL = {v: k for k, v in AUDIO_MODES.items()}
