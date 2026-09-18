# Análise de referência — PixelFenda v0.1.0

## Arquivo analisado

Arquivo fornecido pelo usuário: `snapinsta-1787951701031.mp4`

- Codec de vídeo: H.264
- Resolução: 960×720 (4:3)
- Taxa: 30 fps
- Duração: 36,152 s
- Áudio: AAC estéreo, 44,1 kHz
- Bitrate total aproximado: 4,43 Mb/s

## O que aparece visualmente

A sequência usa famílias de corrupção que mudam ao longo do tempo, em vez de um único filtro estático.

- **0–6 s:** repetição de tiles e colunas, texturas de alta frequência, saturação extrema e regiões que preservam parcialmente o personagem.
- **~6–10 s:** grandes áreas de paleta azul/magenta, blocos isolados e, depois, forte banding horizontal/rainbow.
- **~13–17 s:** colapso de paleta verde/preto, duplicação de regiões inteiras do cenário e fragmentação em blocos.
- **~19–20 s:** a imagem do jogo fica quase íntegra; a corrupção aparece em regiões localizadas e pequenos fragmentos, evidenciando que o efeito pode ser seletivo.
- **~22–27 s:** linhas verticais densas, deslocamentos de endereço/stride, resíduos do personagem e padrões repetidos.
- **~29–36 s:** posterização laranja/roxa, padrões periódicos, grandes regiões monocromáticas e preservação parcial das silhuetas.

## Interpretação técnica

O resultado é compatível visualmente com corrupção de framebuffer/VRAM e não apenas com "pixelização". Os principais componentes que precisam ser simulados em vídeo comum são:

1. framebuffer de baixa resolução com pixels duros;
2. quantização cromática de baixa profundidade;
3. cópia de retângulos/tiles para endereços incorretos;
4. deslocamento de bandas horizontais e verticais;
5. reinterpretação linear de segmentos do buffer (stride/address shift);
6. dano a bitplanes/canais de cor;
7. persistência de dados de quadros anteriores;
8. eventos que duram vários frames, evitando ruído totalmente independente a cada quadro;
9. alternância entre corrupção quase total e regiões quase intactas.

## Como a v0.1.0 reproduz isso

PixelFenda converte cada quadro para um framebuffer virtual de baixa resolução, aplica dithering e empacota os pixels em **RGB555/15 bits**. Em seguida, modifica os próprios dados do buffer com blits de retângulos, deslocamentos, XOR/OR/AND de bitplanes, rolagem linear de memória e reaproveitamento de fragmentos do frame anterior. Por fim, reconverte o buffer e amplia com nearest-neighbour.

Isso é deliberadamente diferente de aplicar uma textura/overlay. A imagem de entrada participa da geração dos próprios padrões de corrupção.

## Limite de fidelidade

O Corrupted Souls Engine descrito na postagem trabalha dentro do contexto de emulação/ROM/VRAM de PlayStation 1. PixelFenda recebe **vídeo já renderizado**, portanto não altera a VRAM real de um jogo nem a lógica da ROM. A v0.1.0 procura reproduzir a linguagem visual e a classe de falhas por uma simulação procedural de memória gráfica.
