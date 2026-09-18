# Validação — PixelFenda v0.4.0 Temporal Director

## Estado

**Development Validated / aguardando validação física da RTX 4060.**

A v0.4.0 preserva o núcleo v0.3.0 já validado fisicamente na RTX 4060 e acrescenta tempo, keyframes, máscaras, tracking e Beat Grid. O ambiente de bancada desta geração não dispõe de contexto NVIDIA/NVENC, por isso o backend GPU novo deve ser novamente confirmado no computador do usuário com `teste_v040.py`.

## Compilação

- `pixelfenda.py`: OK
- todos os módulos em `pixelfenda/*.py`: OK
- `teste_v030.py` (regressão): OK
- `teste_v040.py`: OK

## Regressão v0.3

O autoteste v0.3 foi executado contra a árvore v0.4 para detectar regressões:

- projeto JSON: OK
- LUT 3D: OK
- detector de corte: OK
- Layer Stack CPU: OK
- rota gráfica: fallback CPU esperado nesta máquina
- **30/30 efeitos declarados**: OK
- **19/19 filtros**: OK

Isso inclui os 25 efeitos anteriores e os cinco efeitos v0.4.

## Teste temporal v0.4

Saída da bancada:

```text
PixelFenda v0.4.0 — autoteste Temporal Director
[OK] projeto v4 / campos temporais + máscara
[OK] keyframes/fades/janela temporal — intensidade@1.5s=0.525
[OK] máscara elíptica feather — cobertura média 0.305
[OK] tracking de máscara por optical flow — X 0.322 -> 0.475
[OK] Beat Grid — 15 batidas / 120.0 BPM
[OK] Layer Stack CPU — temporal + máscara + filtro
[OK] rota gráfica + máscara + feedback + filtro: CPU (fallback; GPU OpenGL indisponível)
[OK] render real 45 frames — janela temporal + máscara
[OK] 30 efeitos declarados
[OK] 19 filtros preservados
```

## Projeto v4

Foi verificado roundtrip `save -> load` contendo:

- `start_s` / `end_s`;
- `fade_in_s` / `fade_out_s`;
- keyframes de intensidade, opacidade e modulação;
- easing;
- máscara elíptica;
- feather;
- tracking.

O loader continua tolerante a projetos v3: os novos campos entram pelos defaults da dataclass.

## Keyframes

Cenário de teste:

- camada ativa de 0.5 s a 3.0 s;
- dois keyframes;
- avaliação em 0.1 s -> inativa;
- avaliação em 1.5 s -> ativa, intensidade interpolada 0.525;
- avaliação em 3.2 s -> inativa.

Resultado: OK.

## Máscara

Uma elipse 640×360 com feather foi gerada e validada:

- shape: correto;
- range: 0..1;
- pico > 0.95;
- cobertura média ~0.305;
- blend limitado à máscara: OK.

## Tracking

Foi criado um patch texturizado movendo-se horizontalmente durante nove frames sintéticos. O tracking Lucas–Kanade deslocou o centro normalizado da máscara aproximadamente:

`X 0.322 -> 0.475`

Resultado: OK.

## Beat Grid

Um sinal sintético com transientes a cada 0.5 segundo foi usado como controle. Resultado:

- 15 batidas identificadas;
- BPM estimado: 120.0;
- tolerância esperada do teste: 105–135 BPM.

Resultado: OK.

## Render real curto

Foi criado um MP4 sintético 320×180, 30 fps, 45 quadros. O render v0.4 aplicou:

- Gothic Halo;
- janela temporal;
- fade in/out;
- máscara retangular com feather;
- Silver Gray;
- áudio silencioso;
- libx264.

Resultado: **45/45 quadros e MP4 válido**.

## Interface

A GUI foi instanciada em bancada virtual (Xvfb) e abriu sem TclError. Abas confirmadas:

- Projeto
- Camadas
- Automação
- Tempo & Máscara
- Áudio / Stems
- Fila
- Prévia

Também foram executados programaticamente:

- carregar editor temporal;
- aplicar janela/máscara;
- ativar tracking;
- adicionar keyframe.

Resultado: OK.

## Cinco efeitos v0.4

Todos passaram pelo motor CPU:

1. Temporal Shred
2. Prism Rift
3. Edge Strobe
4. Data Bloom
5. Motion Tunnel

A rota CPU é intencional nesta versão; eles podem ser combinados na mesma pilha com filtros/efeitos OpenGL e NVENC.

## Teste solicitado na RTX 4060

Executar:

```powershell
python .\teste_v040.py
```

Na máquina validada anteriormente, o esperado é:

```text
[OK] rota gráfica + máscara + feedback + filtro: NVIDIA GeForce RTX 4060/PCIe/SSE2
h264_nvenc: OK
hevc_nvenc: OK
av1_nvenc: OK
```

Depois, fazer um render real com:

- uma camada GPU (ex.: Signal Grid);
- uma camada temporal com keyframes;
- uma máscara com tracking;
- um filtro;
- H.264 NVENC.

Se essa etapa passar, a v0.4.0 pode ser promovida para **Stable / Hardware Validated**.
