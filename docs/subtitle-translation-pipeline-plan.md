# Plano Do Pipeline De Legendas

## Objetivo

Reduzir uso desnecessario de Whisper e priorizar legendas textuais existentes antes de transcrever audio. O Bazarr deve continuar como buscador principal de legendas, mas o fallback inteligente deve ficar no `legendas-webui`.

## Decisoes

- Whisper deve ser independente do Bazarr.
- Bazarr deve procurar legendas prontas, principalmente PT-BR e ingles.
- `whisperai` nao deve ficar habilitado como provider automatico do Bazarr.
- `legendas-webui` deve decidir quando traduzir legenda existente, extrair legenda embutida ou chamar Whisper.
- Se existir legenda textual em ingles embutida, ela deve ter alta prioridade porque tende a ser a legenda oficial/curada do release.
- Whisper deve ser ultimo recurso, usado apenas quando nao existir legenda textual aproveitavel.

## Ferramentas Para Audio -> Legenda

Opcoes relevantes:

- `faster-whisper`: boa escolha atual para CPU/GPU, usa CTranslate2 e costuma ser mais eficiente que Whisper Python puro.
- `whisper.cpp`: muito eficiente em CPU, simples de empacotar, bom para hosts sem GPU. Pode ser melhor que o servico atual se a prioridade for uso baixo de recurso.
- `insanely-fast-whisper`: focado em GPU e transformers/flash-attention; menos interessante para CPU.
- `stable-ts`: melhora timestamps e segmentacao, mas e mais uma camada sobre Whisper e pode custar mais processamento.
- `whisperx`: melhora alinhamento e diarizacao, mas e mais pesado e provavelmente desnecessario para legendas domesticas.

Recomendacao inicial: manter `faster-whisper` por enquanto e mover o disparo para o `legendas-webui`. Se CPU/tempo continuar ruim, avaliar trocar o container para `whisper.cpp` ou criar um servico separado baseado em `whisper.cpp`.

## Ordem De Preferencia

Para cada video, o `legendas-webui` deve avaliar nesta ordem:

1. Legenda PT-BR externa existente.
2. Legenda PT-BR embutida existente.
3. Legenda inglesa embutida completa.
4. Legenda inglesa externa.
5. Legenda textual embutida em outro idioma, completa.
6. Legenda textual externa em outro idioma.
7. Whisper a partir do audio.

Justificativa:

- PT-BR encerra o fluxo.
- Ingles embutido costuma vir do proprio release e tende a estar sincronizado com o video.
- Ingles externo tambem e uma boa fonte, mas pode ter drift de timing ou release mismatch.
- Legenda em outro idioma ainda e melhor que Whisper porque ja tem segmentacao e timestamps humanos/curados.
- Whisper e caro e deve ser usado apenas quando nao houver texto aproveitavel.

Observacao: se houver legenda embutida `forced` e uma completa, usar a completa. Legendas `forced` so devem ser usadas se nao houver alternativa e devem ser marcadas como baixa confianca.

## Fluxo Com Bazarr

1. Bazarr procura PT-BR.
2. Se PT-BR for encontrado, o arquivo fica satisfeito.
3. Se PT-BR nao for encontrado, Bazarr pode procurar ingles externo.
4. Bazarr nao deve chamar Whisper automaticamente.
5. `legendas-webui` observa ou varre a biblioteca e decide o fallback.

Configuracao sugerida no Bazarr:

- Perfil com `Portuguese (Brazil)` e `English`.
- Cutoff em `Portuguese (Brazil)`.
- Providers sem credenciais invalidas ou throttling recorrente.
- `embeddedsubtitles` habilitado para indexar legendas embutidas.
- `whisperai` desabilitado como provider automatico.

## Fluxo No Legendas-Webui

### Scanner

Adicionar uma varredura periodica alem do watcher atual:

- Localizar videos em `/media/movies` e `/media/series`.
- Para cada video, identificar legendas externas relacionadas.
- Rodar `ffprobe` para identificar streams de legenda embutida.
- Montar uma lista de candidatos com idioma, origem, codec, forced/full e score.

### Traducao

Se houver candidato textual nao PT-BR:

- Se for externa `.srt`, traduzir direto.
- Se for externa `.ass` ou `.ssa`, converter para `.srt` antes de traduzir.
- Se for embutida, extrair com `ffmpeg`, converter se necessario e traduzir.
- Salvar resultado como `*.pt-BR.srt` ao lado do video.
- Nao sobrescrever `*.pt-BR.srt` existente.

### Whisper

Se nao houver nenhuma legenda textual aproveitavel:

- Exibir botao manual `Gerar legenda por audio`.
- Opcionalmente permitir modo automatico depois que o fluxo estiver estavel.
- Gerar `*.en.srt` ou diretamente `*.pt-BR.srt`, dependendo da qualidade do resultado testado.

Recomendacao inicial: gerar `*.en.srt` e deixar o tradutor criar `*.pt-BR.srt`, para manter rastreabilidade.

## Mudancas De Compose E Ownership

Para extrair legendas embutidas, o `legendas-webui` precisa de `ffmpeg`/`ffprobe` no container.

Para Whisper independente, existem duas abordagens:

### Opcao A: Upload Para API Do Whisper

- `legendas-webui` le o arquivo em `/media` e faz upload para `whisper-asr`.
- `whisper-asr` nao precisa montar `/media`.
- Evita problemas de ownership no `whisper-asr`.
- Pode consumir mais I/O e memoria por upload de arquivos grandes.

### Opcao B: Montar Media No Whisper

- Montar `./media:/media:ro` no `whisper-asr`.
- `whisper-asr` le o video direto do bind mount.
- O mount deve ser somente leitura.
- O `whisper-asr` nao deve escrever em `media/`.
- `legendas-webui`, que ja roda como `${PUID}:${PGID}`, continua sendo o unico responsavel por gravar `*.en.srt` e `*.pt-BR.srt`.

Recomendacao: usar a Opcao B se a API suportar path local; caso contrario usar upload. Em ambos os casos, preservar ownership atual: `media/` gravavel por `PUID:PGID` e leitura permitida aos containers que precisam analisar midia.

## Melhorias Na Interface

- Mostrar candidatos detectados por video: PT-BR, ingles, outros idiomas, embutidas e externas.
- Mostrar origem da legenda usada para traducao.
- Mostrar quando Whisper esta rodando e qual arquivo esta sendo processado.
- Corrigir estado `Carregando...` permanente quando o fetch/render falha.
- Iniciar watcher no startup do container, nao apenas no primeiro request HTTP.
- Adicionar acoes manuais: `Traduzir melhor legenda`, `Extrair legenda embutida`, `Gerar via Whisper`.

## Fases De Implementacao

### Fase 1

- Remover `whisperai` dos providers automaticos do Bazarr.
- Adicionar `ffmpeg`/`ffprobe` no container `legendas-webui`.
- Corrigir UI presa em `Carregando...`.
- Iniciar watcher no startup.
- Implementar scanner de legendas externas nao PT-BR.

### Fase 2

- Implementar deteccao de streams embutidos com `ffprobe`.
- Extrair legendas embutidas completas com `ffmpeg`.
- Converter ASS/SSA para SRT.
- Traduzir legenda extraida via Ollama.

### Fase 3

- Adicionar botao manual para Whisper.
- Integrar Whisper diretamente pela UI.
- Avaliar `faster-whisper` atual contra `whisper.cpp`.
- Adicionar modo automatico de Whisper apenas como ultimo recurso, se desejado.

## Criterios De Sucesso

- Nenhum audio e transcrito se houver legenda textual aproveitavel.
- Legendas PT-BR existentes nunca sao sobrescritas.
- Legendas inglesas embutidas sao usadas antes de ingles externas.
- Whisper fica controlado pelo `legendas-webui`, nao pelo Bazarr.
- A UI mostra o motivo da escolha de cada acao.
- O container que escreve em `media/` continua rodando como `${PUID}:${PGID}`.
