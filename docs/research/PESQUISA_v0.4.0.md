# Pesquisa técnica — PixelFenda v0.4.0 Temporal Director

Pesquisa consolidada em agosto de 2026. A v0.4.0 preserva a arquitetura v0.3.0 e acrescenta controle temporal/espacial por camada.

## 1. Keyframes e interpolação

O motor passa a tratar intensidade, opacidade e força de modulação como parâmetros que podem variar no tempo. Cada camada possui uma janela `start_s/end_s`, `fade_in_s/fade_out_s` e uma lista serializável de keyframes. A interpolação oferece Linear, Smoothstep, Ease In, Ease Out e Hold.

A implementação é interna e determinística; projetos v4 continuam sendo JSON legível.

## 2. Tracking de máscara por Lucas–Kanade

O OpenCV documenta `cv.calcOpticalFlowPyrLK()` como implementação de fluxo óptico Lucas–Kanade piramidal para um conjunto esparso de pontos, e demonstra seu uso em conjunto com `cv.goodFeaturesToTrack()` para acompanhar pontos ao longo de um vídeo.

Fontes:
- https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html
- https://docs.opencv.org/4.10.0/dc/d6b/group__video__track.html

A v0.4.0 usa exatamente essa família de técnicas para mover o **centro da máscara**, sem tentar segmentar semanticamente pessoas/objetos. Pontos visuais fortes são selecionados dentro da região da máscara e o deslocamento mediano dos pontos válidos desloca o centro. O método é leve, local e não exige `opencv-contrib`, modelo neural nem API.

## 3. Máscaras

Foram implementadas cinco famílias:
- tela inteira;
- retângulo;
- elipse;
- gradiente linear;
- vinheta/centro.

Cada uma pode usar feather e inversão. Retângulo e elipse podem ativar tracking. A máscara atua **depois** do efeito/filtro/LUT e antes da composição final do layer, portanto também funciona com blend modes.

## 4. Beat Grid

O material de referência do librosa descreve beat tracking como uma sequência de três operações: medir onset strength, estimar tempo e selecionar picos coerentes com o tempo. A v0.4.0 não adiciona librosa como dependência obrigatória; reutiliza o sinal de onset/transiente já produzido pelo motor FFT do PixelFenda e aplica seleção de picos com período refratário e estimativa robusta de BPM.

Fontes:
- https://librosa.org/doc/latest/auto_tutorials/01-intro/06-rhythm.html
- https://librosa.org/doc/0.10.2/generated/librosa.beat.beat_track.html

O Beat Grid serve para **gerar keyframes reproduzíveis**, não para alterar silenciosamente os efeitos. A seed e os keyframes ficam salvos no projeto.

## 5. GPU / compute shaders

ModernGL 5.12 expõe `Context.compute_shader()` e suporte a storage buffers e imagens. Isso torna possível, em versões futuras, mover operações como optical flow aproximado, LUT 3D e alguns masks para compute shaders.

Fonte:
- https://moderngl.readthedocs.io/_/downloads/en/stable/pdf/

A v0.4.0 deliberadamente **não substitui** a rota OpenGL fragment-shader já validada na RTX 4060. Estabilidade e reprodutibilidade têm prioridade. Máscaras e tracking ficam em CPU; o conteúdo da camada continua usando GPU sempre que a família de efeito/filtro já for compatível.

## 6. Render retomável

O FFmpeg possui segment muxer e concat demuxer, permitindo pipelines segmentados. Contudo, efeitos PixelFenda como VRAM persistente e feedback possuem estado temporal entre quadros. Retomar arbitrariamente no meio do vídeo sem serializar esse estado mudaria a imagem. Por isso a v0.4.0 não anuncia “resume render” ainda.

Fontes:
- https://www.ffmpeg.org/ffmpeg-formats.html#segment
- https://ffmpeg.org/faq.html

Uma versão futura poderá criar checkpoints de estado por cena, em vez de simplesmente dividir o arquivo.
