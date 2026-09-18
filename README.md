# PixelFenda v0.4.0 — Temporal Director

**PixelFenda** é um processador autoral de vídeo/glitch art. A v0.4.0 preserva a base **v0.3.0 Stable / Hardware Validated** e acrescenta direção temporal e espacial por camada: keyframes, janelas de tempo, fades, máscaras, tracking e Beat Grid.

> A família VRAM continua sendo uma simulação artística de memória gráfica sobre vídeo comum; PixelFenda não executa ROMs e não depende de um emulador de PlayStation.

## Novidades da v0.4.0

### Temporal Director
Cada camada pode definir:
- início e fim em segundos;
- fade in / fade out;
- keyframes de **intensidade**;
- keyframes de **opacidade**;
- keyframes de **força de modulação**;
- interpolação Linear, Smooth, Ease In, Ease Out ou Hold.

Uma camada pode, por exemplo, existir somente de 12.5 s a 18.0 s, entrar suavemente em 0.6 s, atingir 100% de intensidade no refrão e desaparecer no corte seguinte.

### Máscaras por camada
Modos:
- Tela inteira;
- Retângulo;
- Elipse;
- Gradiente linear;
- Vinheta / centro.

Parâmetros: centro X/Y, largura, altura, feather, ângulo e inversão. A máscara é aplicada ao resultado da camada e respeita os blend modes da v0.3.

### Tracking local
Retângulos e elipses podem acompanhar movimento. O tracking usa pontos Shi–Tomasi + optical flow Lucas–Kanade piramidal (`goodFeaturesToTrack` + `calcOpticalFlowPyrLK`). Não há modelo neural obrigatório.

### Beat Grid
O PixelFenda transforma o canal de transientes FFT em uma grade de batidas, estima BPM e pode gerar automaticamente pulsos de intensidade nos keyframes. O resultado fica salvo no projeto e pode ser editado manualmente.

### Novos efeitos autorais v0.4
Além dos 25 efeitos da v0.3, entram cinco famílias temporais/espaciais:
- **Temporal Shred** — tiras de memória entre o frame atual e histórico;
- **Prism Rift** — fratura RGB radial sensível a movimento/beat;
- **Edge Strobe** — bordas pulsadas por beat/agudos;
- **Data Bloom** — highlights digitais, bloom e deslocamento de blocos;
- **Motion Tunnel** — feedback/zoom temporal dirigido pelo movimento.

Esses cinco efeitos possuem fallback CPU nesta versão. Eles podem coexistir com filtros e efeitos GPU na mesma pilha; a RTX continua sendo usada nas camadas OpenGL compatíveis e na codificação NVENC.

### Compatibilidade preservada
- 30 efeitos;
- 19 filtros;
- VRAM virtual persistente 1024×512×16-bit;
- Layer Stack de até 12 camadas;
- 9 blend modes;
- LUT `.cube` 1D/3D;
- scene detector e Auto Scene Mutator;
- FFT e optical flow;
- Demucs opcional;
- fila de render;
- H.264 / HEVC / AV1 NVENC;
- ModernGL/OpenGL com fallback CPU.

## Instalação Windows

Recomendado: Python 3.13 x64 e driver NVIDIA atualizado.

```powershell
cd C:\caminho\PixelFenda_v0_4_0
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Ou execute `install_windows.bat`.

Abrir:

```powershell
python .\pixelfenda.py
```

## Autoteste v0.4.0

Antes do primeiro render:

```powershell
python .\teste_v040.py
```

Ele verifica:
1. projeto JSON format v4;
2. keyframes, fades e janela temporal;
3. máscara com feather;
4. tracking Lucas–Kanade em objeto sintético;
5. Beat Grid em sinal sintético de 120 BPM;
6. Layer Stack CPU com tempo + máscara + filtro;
7. rota gráfica com máscara + feedback + filtro;
8. render real curto;
9. detecção H.264/HEVC/AV1 NVENC.

Na RTX 4060 validada nas versões anteriores, o item 7 deve identificar `NVIDIA GeForce RTX 4060/PCIe/SSE2` e os três NVENC devem retornar `OK`.

## Interface

As abas são:
- **Projeto** — entrada, saída, resolução, encoder, GPU e seed;
- **Camadas** — pilha de efeitos/filtros/LUTs;
- **Automação** — reatividade e cenas;
- **Tempo & Máscara** — keyframes, janela temporal, máscaras, tracking e Beat Grid;
- **Áudio / Stems** — original, mute, replace, mix e Demucs opcional;
- **Fila** — vários vídeos com o mesmo projeto;
- **Prévia** — comparação Antes/Depois em posição ajustável do vídeo.

## Workflow sugerido

1. Escolha o vídeo e a resolução.
2. Monte a pilha na aba **Camadas**.
3. Selecione uma camada e abra **Tempo & Máscara**.
4. Defina onde a camada começa/termina.
5. Adicione keyframes ou analise o Beat Grid.
6. Defina uma máscara; se necessário, ative tracking.
7. Gere a prévia em diferentes posições do vídeo.
8. Renderize com `Automático` ou NVENC explícito.

## Projeto v4

Arquivos `.pixelfenda.json` continuam legíveis. A v0.4 acrescenta por layer, entre outros campos:

```json
{
  "start_s": 4.5,
  "end_s": 12.0,
  "fade_in_s": 0.4,
  "fade_out_s": 0.6,
  "keyframe_ease": "smooth",
  "keyframes": [
    {"time": 5.0, "intensity": 0.4, "opacity": 0.7},
    {"time": 7.0, "intensity": 1.0, "opacity": 1.0}
  ],
  "mask_kind": "ellipse",
  "mask_x": 0.5,
  "mask_y": 0.45,
  "mask_w": 0.55,
  "mask_h": 0.70,
  "mask_feather": 0.12,
  "mask_track": true
}
```

Projetos v3 continuam carregando; campos novos recebem defaults.

## Limitações conscientes

- O tracking v0.4 movimenta o centro da máscara; ele não faz segmentação semântica de pessoa/cabelo/objeto.
- Uma prévia isolada em posição arbitrária não possui todo o histórico anterior do tracker; o render sequencial é a referência para tracking temporal.
- Mudanças bruscas de iluminação, oclusões e cortes podem exigir reposicionar/reiniciar a máscara.
- Beat Grid é um detector leve baseado no onset já extraído pelo PixelFenda; não pretende substituir uma DAW.
- LUT customizada continua em CPU nesta versão.
- “Resume render” não foi ativado porque VRAM/feedback possuem estado temporal e um resume ingênuo mudaria o resultado.

## Pesquisa

Veja `docs/research/PESQUISA_v0.4.0.md`.

## Licença

MIT. Consulte `LICENSE`.
