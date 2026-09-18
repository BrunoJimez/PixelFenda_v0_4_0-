# Validação — PixelFenda v0.2.0

Data da bancada: 28/08/2026.

## Testes executados neste build

- Compilação Python (`compileall`) de todo o pacote: OK.
- Preview CPU de todos os **20 efeitos**: OK.
- Preview CPU de todos os **19 filtros**: OK.
- Render real de VRAM persistente + filtro + movimento: OK.
- Modo apenas efeito: OK.
- Modo apenas filtro: OK.
- Modo efeito + filtro: OK.
- Modo sem efeito e sem filtro (conversão): OK.
- Render real de efeito procedural + filtro + análise de áudio/movimento: OK.
- Áudio original: OK.
- Vídeo silencioso: OK (arquivo final sem stream de áudio).
- Substituição do áudio por nova faixa: OK.
- Mix de áudio original + faixa adicional: OK.
- Fallback `GPU=Auto` para CPU quando ModernGL/OpenGL não está disponível: OK.
- Saída H.264/libx264: OK.

## GPU/NVENC

O ambiente usado para construir este pacote não disponibiliza um contexto ModernGL compatível nem uma RTX 4060. Por isso, os shaders foram incluídos e validados estaticamente pelo código, mas **o caminho OpenGL não foi declarado como testado em hardware NVIDIA nesta bancada**.

No computador de destino, execute:

```powershell
python diagnostico_gpu.py
```

O script testa criação do contexto OpenGL e disponibilidade de `h264_nvenc`, `hevc_nvenc` e `av1_nvenc`. O programa mantém fallback automático para CPU quando `Processamento = Automático`.

## Folhas visuais

- `TEST_CARD_v0.2.0.png`: cartão de teste autoral, sem imagens de terceiros.
- `TESTE_VISUAL_EFEITOS_v0.2.0.jpg`: matriz dos 20 efeitos usando o cartão de teste.
- `TESTE_VISUAL_FILTROS_v0.2.0.jpg`: matriz dos 19 filtros usando o cartão de teste.

Os arquivos contidos em `efeitos.rar` e `filtros.rar` foram utilizados apenas como referências de análise e **não são distribuídos dentro do programa**.
