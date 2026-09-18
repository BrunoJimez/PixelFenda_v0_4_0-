# Pesquisa técnica — PixelFenda v0.3.0

Pesquisa de arquitetura realizada para a versão Layer Mutation Studio.

## 1. Detecção de cortes e automação por cena

PySceneDetect é uma referência madura para detecção de cenas. Sua documentação descreve o `ContentDetector` como um detector que compara alterações de conteúdo entre quadros no espaço HSV, e o `AdaptiveDetector` como uma alternativa que reduz falsos cortes em cenas com movimento rápido.

A v0.3.0 não adiciona PySceneDetect como dependência obrigatória. Em vez disso, implementa um detector interno leve que reduz os quadros e calcula uma diferença HSV normalizada. A opção mantém o instalador simples e é suficiente para disparar automações artísticas, embora não pretenda substituir uma ferramenta dedicada de edição/segmentação.

Fontes:
- https://www.scenedetect.com/docs/latest/
- https://www.scenedetect.com/docs/api/detectors.html
- https://www.scenedetect.com/api/

## 2. LUTs `.cube`

O formato Cube é textual e pode representar tabelas 1D e 3D. Os cabeçalhos típicos incluem `LUT_1D_SIZE`, `LUT_3D_SIZE`, `DOMAIN_MIN` e `DOMAIN_MAX`, seguidos pelos valores RGB da tabela.

A v0.3.0 implementa leitura de LUT 1D/3D e interpolação trilinear para 3D. A execução é dividida em blocos de linhas para evitar a criação simultânea de oito volumes de corners em resolução Full HD.

Referência de formato:
- https://github.com/CommandPost/ResolveCafe/blob/main/docs/developers/luts.md

## 3. GPU e possível evolução de LUT 3D

ModernGL expõe `Context.texture3d()`, e a documentação descreve `Texture3D` como um objeto OpenGL que pode ser usado como fonte de leitura em shaders. Isso permite uma evolução futura em que LUTs customizadas sejam carregadas como texturas 3D na GPU.

Na v0.3.0, a prioridade foi compatibilidade e correção: as LUTs customizadas usam CPU, enquanto os 16 efeitos OpenGL e os 19 filtros compatíveis continuam usando a RTX quando disponível.

Fonte:
- https://moderngl.readthedocs.io/en/latest/reference/texture3d.html

## 4. Separação de voz e instrumental

Demucs é um sistema de source separation que pode separar stems como vocals, drums, bass e other. A própria documentação oferece `--two-stems=vocals` para obter voz e acompanhamento e permite escolher o dispositivo com `--device`, cujo padrão é CUDA quando disponível no PyTorch.

Por ser um módulo de IA pesado (PyTorch + pesos de modelo), ele foi mantido **opcional**. O PixelFenda procura um ambiente `.venv_demucs` separado ou um Python especificado em `PIXELFENDA_DEMUCS_PYTHON`.

Fontes:
- https://github.com/facebookresearch/demucs
- https://github.com/facebookresearch/demucs/blob/main/demucs/separate.py
- https://github.com/facebookresearch/demucs/blob/main/docs/windows.md

## 5. Layer Stack e estado temporal

Um desafio técnico de múltiplas camadas é que feedback, VRAM e efeitos temporais não devem compartilhar acidentalmente o mesmo quadro anterior. A v0.3.0 mantém estado por camada:

- cada camada VRAM possui sua própria memória virtual persistente;
- cada efeito CPU possui seu próprio `CPUEffectEngine`;
- efeitos OpenGL que dependem do quadro anterior guardam um `prev_gpu` por camada e injetam esse quadro antes do shader;
- filtros GPU que não dependem de histórico podem reutilizar o pipeline OpenGL.

Isso reduz consumo de contexto/VRAM em comparação com abrir um contexto OpenGL completo por camada e evita que o feedback de uma camada seja contaminado pelo resultado intermediário de outra.

## 6. Blend modes

A v0.3.0 implementa composição em float normalizado para:

- Normal
- Screen
- Multiply
- Add
- Difference
- Overlay
- Soft Light
- Lighten
- Darken

A opacidade é aplicada depois da função de blend. A intensidade continua separada e controla a operação interna da camada.

## 7. Auto Scene Mutator

O objetivo do modo não é editar o vídeo por cenas, mas usar os cortes como eventos artísticos. A cada corte:

- o contador de cena avança;
- camadas podem resetar memória/feedback;
- no modo Mutator, uma RNG com seed do projeto cria novos ganhos por camada;
- a ordem das camadas não muda, garantindo reprodutibilidade e evitando reconstrução do pipeline durante o render.

Com a mesma seed, vídeo e configuração, a sequência de variações é reproduzível.
