# Validação — PixelFenda v0.3.0

## Estado da build

**Stable / Hardware Validated.** A v0.3.0 foi validada em bancada local e, posteriormente, no computador do usuário com **NVIDIA GeForce RTX 4060**, usando `teste_v030.py`. O autoteste confirmou Layer Stack, LUT 3D, detector de cena, novos shaders OpenGL e H.264/HEVC/AV1 NVENC.

## Testes executados

### Compilação
- `pixelfenda.py`: OK
- todos os módulos em `pixelfenda/*.py`: OK
- `teste_v030.py`: OK

### Modelos/projetos
- `LayerSpec`: serialização e normalização: OK
- `ProjectDocument`: save/load JSON: OK
- Projeto com 4 camadas: roundtrip OK

### Layer Stack
- efeito + efeito + filtro + LUT: OK
- blend Screen: OK
- blend Normal: OK
- modulação Beat: OK
- modulação Motion: OK
- Auto Scene Mutator: OK
- estado VRAM por camada: OK em CPU

### Blend modes
Todos retornaram imagem `uint8` válida:
- Normal
- Screen
- Multiply
- Add
- Difference
- Overlay
- Soft Light
- Lighten
- Darken

### Efeitos
- 25/25 presets declarados passaram por processamento CPU/fallback.
- Novos presets: Cyber Wire, Liquid Chrome, PSX Dither, Gothic Halo, Signal Grid.

### Filtros
- 19/19 filtros visuais passaram por processamento CPU/fallback.

### LUT
- parser `.cube`: OK
- `LUT_3D_SIZE 17`: OK
- trilinear interpolation: OK
- Cobalt Noir: OK
- Amber Crypt: OK
- Chrome Ice: OK

### Detecção de cena
- detector HSV: OK
- corte sintético preto -> branco: detectado
- vídeo sintético de 60 quadros: corte no frame 30 detectado com score ~0.617
- CLI `--analyze-scenes`: OK

### Render real em bancada
Entrada sintética:
- 320×240
- 30 fps
- 60 quadros

Pilha:
1. Cyber Wire — motion modulated
2. Cold Archive
3. LUT Amber Crypt

Configuração:
- CPU
- libx264
- silent
- Auto Scene Mutator

Resultado:
- 60/60 quadros: OK
- arquivo MP4 final: OK
- duas cenas registradas: OK

### CLI
- `--help`: OK
- efeito + filtro: OK
- render parcial com `--max-seconds`: OK
- JSON de resultado: OK
- análise de cenas em JSON: OK

### GPU/NVENC — validação física em RTX 4060
Autoteste executado no computador do usuário:

```text
[OK] projeto JSON / 4 camadas
[OK] LUT .cube 3D — PixelFenda_ChromeIce 17³
[OK] detector de corte de cena
[OK] Layer Stack CPU — efeito + efeito + filtro + LUT + blends/modulação
[OK] rota gráfica / novos shaders + feedback + filtro: NVIDIA GeForce RTX 4060/PCIe/SSE2
[OK] 25 efeitos declarados
[OK] 19 filtros declarados
h264_nvenc: OK
hevc_nvenc: OK
av1_nvenc: OK
```

A pilha GPU do autoteste inclui Cyber Wire, Liquid Chrome, PSX Dither, Gothic Halo, Signal Grid, Spectral Echo e Vintage 70. Portanto a v0.3.0 teve validada fisicamente a composição multi-layer com novos shaders, feedback temporal, filtro e NVENC na RTX 4060.
