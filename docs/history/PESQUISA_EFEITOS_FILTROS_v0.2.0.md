# Pesquisa técnica e estética — PixelFenda v0.2.0

Pesquisa realizada em agosto de 2026 para orientar a arquitetura da v0.2.0.

## 1. VRAM 1024×512

A documentação técnica PSX-SPX descreve o PlayStation com 1 MB de VRAM, usado por framebuffer(s), texture page(s) e palettes. Em formato 16-bit/halfword, a área endereçável padrão é 1024×512. A v0.2.0 passa, portanto, de um framebuffer reduzido independente para uma memória virtual persistente 1024×512×16-bit com regiões funcionais e vazamento entre páginas.

Fonte: PSX-SPX, Graphics Processing Unit / VRAM Overview.  
https://psx-spx.consoledev.net/graphicsprocessingunitgpu/

## 2. GPU na RTX 4060

A RTX 40 é baseada em Ada Lovelace e inclui NVENC de 8ª geração com AV1. Para os efeitos, o PixelFenda usa uma rota OpenGL/fragment-shader por ModernGL; para a saída, usa NVENC via FFmpeg quando disponível.

Fontes:  
https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/  
https://developer.nvidia.com/video-codec-sdk  
https://moderngl.readthedocs.io/en/latest/reference/moderngl.html

## 3. Movimento reativo

OpenCV define optical flow como o campo de movimento aparente entre quadros consecutivos e fornece Lucas-Kanade e Farneback. A v0.2.0 usa Farneback em resolução reduzida para obter força e direção médias, suficientes para dirigir feedback, tearing, datamosh procedural e deslocamento.

Fonte: https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html

## 4. Áudio reativo

Visualizadores musicais normalmente extraem waveform/frequência via FFT. A v0.2.0 decodifica áudio pelo FFmpeg e calcula FFT em NumPy, extraindo RMS, graves, médios, agudos e onset. Isso evita serviços online e APIs pagas.

Referência conceitual: MDN, Web Audio visualizations / AnalyserNode.  
https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Visualizations_with_Web_Audio_API

## 5. Filme / vintage / cinematic

O Film Look Creator do DaVinci Resolve reúne propriedades típicas de emulação fotoquímica: contraste/cor, halation, film gate, flicker, weave, vignette, bloom e outras características. Essa taxonomia orientou os filtros Vintage 70/90, Cold Archive, Bleach Bypass e Odisseia 70.

Fonte: Blackmagic Design, DaVinci Resolve 19 New Features Guide / Film Look Creator.  
https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_19_New_Features_Guide.pdf

## 6. Instagram / social filters

O ecossistema social popularizou gradações simples e reconhecíveis: contraste frio e saturado, muted/faded, preto e branco, warm/cool. Fontes de referência descrevem Clarendon como mais frio e contrastado, Gingham como muted/flat e Moon/Willow como preto e branco. Em vez de copiar LUTs exatos, PixelFenda traduz essas famílias em `Social Cool`, `Muted Linen` e `Soft B&W`.

Fontes:  
https://later.com/blog/how-to-post-on-instagram/  
https://blog.hootsuite.com/how-to-edit-instagram-photos/

## 7. Odisseia 70

Em artigo técnico publicado em 24/08/2026, Kodak registra que *The Odyssey* foi o primeiro longa narrativo fotografado integralmente com câmeras IMAX em 15-perf 65mm. Hoyte van Hoytema usou VISION3 250D 5207 em exteriores/interiores claros de dia e VISION3 500T 5219 em baixa luz/noite. O artigo também descreve dailies em película, color timing tradicional e um DCP digital orientado pelo print fotoquímico.

O preset `Odisseia 70` **não é um LUT oficial nem uma tentativa de clonagem exata**. É uma interpretação autoral desses princípios: imagem grande/limpa, saturação contida, grão fino, highlights levemente quentes, sombras neutras/frias, bloom/halation discreto e contraste moderado.

Fonte: Kodak Motion Picture, *Shooting entirely on Kodak IMAX 70mm film... The Odyssey*.  
https://www.kodak.com/en/motion/blog-post/the-odyssey/

## 8. Famílias adicionais escolhidas para a v0.2.0

- ASCII/ANSI raster e terminal;
- digital rain/code fall;
- CRT: scanlines, channel separation, curvatura e phosphor-like attenuation;
- VHS: jitter horizontal, chroma offset e ruído temporal;
- pixel sorting por luminância;
- slit-scan/scanline displacement;
- recursive video feedback;
- motion-vector-like datamosh procedural;
- bloom/halo de silhueta;
- neon edge extraction;
- dithering/posterização para sci-fi PC/console 90s;
- colagem brutalista com cópia/zoom de regiões.

Esses módulos foram escolhidos por combinar bem com shaders paralelos e/ou operações matriciais, dando espaço real para a RTX 4060 sem tornar o programa dependente de IA generativa ou de API paga.
