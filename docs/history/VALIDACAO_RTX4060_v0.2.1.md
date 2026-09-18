# PixelFenda v0.2.1 — Validação RTX 4060

## Ambiente validado

- Sistema operacional: Windows 10 (10.0.19045)
- GPU: NVIDIA GeForce RTX 4060, 8 GB
- Backend gráfico: ModernGL / OpenGL
- FFmpeg principal: build gyan.dev com NVENC habilitado

## Autoteste executado

Comando:

```powershell
python .\teste_hotfix_v021.py
```

Resultado observado:

```text
[OK] vram_mais_filtro: NVIDIA GeForce RTX 4060/PCIe/SSE2
[OK] shader_mais_filtro: NVIDIA GeForce RTX 4060/PCIe/SSE2
h264_nvenc: OK
hevc_nvenc: OK
av1_nvenc: OK
AUTOTESTE CONCLUÍDO.
```

## Teste funcional

Após o autoteste, o aplicativo foi iniciado com:

```powershell
python .\pixelfenda.py
```

Foi realizado um render de vídeo com **efeito e filtro habilitados simultaneamente**, cenário que falhava na v0.2.0. O render foi concluído com sucesso na v0.2.1.

## Bugs verificados como corrigidos

- uniform GLSL `u_treble` otimizado pelo driver não derruba mais o pipeline;
- efeito + filtro pode usar a rota GPU sem a exceção anterior;
- mensagens de erro do worker Tkinter são preservadas;
- detecção de NVENC não usa mais o probe 64×64 que causava falso negativo;
- H.264, HEVC e AV1 NVENC foram confirmados em teste real.

## Observação

A validação comprova o funcionamento desta combinação específica de hardware/driver/software. Outros computadores podem exigir drivers ou builds de FFmpeg diferentes.
