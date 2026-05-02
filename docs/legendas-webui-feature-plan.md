# Plano De Features Do Legendas-Webui

## Objetivo

Melhorar o `legendas-webui` para operar mais como uma central de legendas da biblioteca: buscar arquivos de midia/legenda, acionar transcricao por audio quando necessario e visualizar legendas recentes sem sair do dashboard.

Features pedidas:

1. Campo de busca para candidatos a traducao, preferencialmente pesquisando qualquer arquivo da biblioteca e nao apenas candidatos pendentes.
2. Botao para invocar Whisper e gerar uma nova legenda em ingles, subindo o container sob demanda e parando ao finalizar.
3. Visualizador de legendas na lista de legendas recentes, abrindo outra pagina.

## Estado Atual

- A tela principal esta em `scripts/webui-legendas/templates/index.html`, com CSS e JS inline.
- `main.py` expoe APIs para status, candidatos, fila de traducao e legendas recentes.
- `scanner.py` ja conhece `MEDIA_DIR`, raizes `movies`/`series`, extensoes de video, extensoes de legenda e metodos para identificar idioma por nome.
- `extractor.py` ja usa `ffprobe` e `ffmpeg` via `run_exec`, util para carregar informacoes de streams embutidos.
- `whisper-asr` esta no profile `transcription`, entao a stack padrao nao deve mante-lo em RAM.
- `legendas-webui` ja monta `/var/run/docker.sock:ro` para consulta, mas ainda nao tem permissao explicita planejada para executar `docker compose up/stop` ou iniciar containers.

## Decisoes De Produto

- A busca deve pesquisar a biblioteca inteira, nao apenas `candidate_cache`.
- O resultado de busca deve mostrar videos, legendas externas e status resumido de cada item.
- Metadados caros, como streams embutidos via `ffprobe`, devem ser carregados sob demanda ao expandir/selecionar um resultado, nao em toda digitacao.
- Whisper deve ser acao manual por arquivo de video, nunca automatico nesta fase.
- Whisper deve gerar `*.en.srt`; a traducao PT-BR continua pelo fluxo existente de traducao.
- O visualizador deve ser somente leitura e deve validar que o arquivo solicitado esta dentro de `MEDIA_DIR`.

## Feature 1: Busca Global De Arquivos

### Comportamento Desejado

- Adicionar campo de busca na area de `Candidatos Para Traducao` ou em uma nova secao `Buscar Na Biblioteca` acima dela.
- Pesquisar por nome de arquivo e caminho relativo dentro de `/media/movies` e `/media/series`.
- Aceitar busca por partes do nome, temporada/episodio, extensao e idioma aparente, por exemplo `s01e03`, `.mkv`, `.en.srt`, `pt-BR`.
- Retornar videos e legendas, mesmo quando nao sao candidatos pendentes.
- Para videos, mostrar resumo rapido:
  - Nome do arquivo.
  - Tipo `video`.
  - Caminho relativo.
  - Se existe `*.pt-BR.srt` externo.
  - Se existe `*.en.srt` externo.
  - Acoes: `Detalhes`, `Traduzir melhor legenda`, `Gerar EN via Whisper` quando aplicavel.
- Para legendas, mostrar resumo rapido:
  - Nome do arquivo.
  - Tipo `subtitle`.
  - Idioma inferido pelo nome.
  - Caminho relativo.
  - Acoes: `Visualizar`, `Traduzir` quando nao for PT-BR.

### Implementacao Recomendada

Criar funcoes novas em `scanner.py`:

- `search_media(query, limit=50)`: varre `media_roots()` e retorna resultados leves.
- `build_file_summary(path)`: classifica como video/subtitle/outro suportado e adiciona informacoes baratas.
- `get_video_details(path)`: carrega informacoes sob demanda, incluindo `ffprobe_subtitles(path)` e legendas externas relacionadas.

Adicionar endpoints em `main.py`:

```text
GET /api/search?q=<texto>&limit=50
GET /api/media/details?path=<path-absoluto-ou-relativo>
```

Recomendacao de seguranca:

- Preferir aceitar path relativo a `MEDIA_DIR` no frontend.
- No backend, resolver com `Path.resolve()` e rejeitar qualquer path fora de `MEDIA_DIR`.
- Nunca retornar conteudo de arquivos de video, apenas metadados.

### UI

- Manter debounce simples no JS, por exemplo 300ms apos digitacao.
- Mostrar estados `Digite ao menos 2 caracteres`, `Buscando...`, `Nenhum resultado` e erro de API.
- Ao clicar em `Detalhes`, chamar `/api/media/details` e renderizar:
  - Legendas externas relacionadas.
  - Streams embutidos detectados.
  - Saidas esperadas: `.en.srt` e `.pt-BR.srt`.
  - Acoes disponiveis por item.

### Performance

- A primeira versao pode varrer filesystem sob demanda, porque a biblioteca e local e o limite e baixo.
- Se a busca ficar lenta, adicionar cache em memoria com TTL curto, por exemplo 60s, ou reutilizar o ciclo periodico do scanner.
- Nao rodar `ffprobe` durante a busca textual; fazer isso apenas em `Detalhes`.

## Feature 2: Botao Para Gerar Legenda Inglesa Via Whisper

### Comportamento Desejado

- Em resultados de video e/ou detalhes do video, exibir botao `Gerar EN via Whisper`.
- Ao clicar:
  - Enfileirar um job de transcricao.
  - Subir `whisper-asr` se nao estiver rodando.
  - Aguardar a API responder saudavel.
  - Enviar o video para transcricao.
  - Salvar resultado como `*.en.srt` ao lado do video.
  - Parar `whisper-asr` ao final somente se o proprio job iniciou o container.
  - Atualizar status da UI em tempo real via WebSocket ou polling existente.

### Regras De Seguranca E Consistencia

- Nao sobrescrever `*.en.srt` existente por padrao.
- Adicionar confirmacao se ja existir `.en.srt` e uma opcao futura para regenerar com sufixo, por exemplo `.whisper.en.srt`.
- Apenas aceitar arquivos de video dentro de `MEDIA_DIR`.
- Permitir apenas um job de Whisper por vez para evitar pico de RAM/CPU.
- Se o container ja estava rodando antes do job, nao para-lo automaticamente ao final.
- Se o job falhar apos iniciar o container, ainda parar o container quando ele tiver sido iniciado pelo proprio job.
- Registrar erro claro no status do job e na UI.

### Integracao Com Docker

Existem duas abordagens possiveis:

#### Opcao A: Docker CLI Pelo Socket

- O `legendas-webui` executa comandos Docker/Compose para `docker compose up -d whisper-asr` e `docker compose stop whisper-asr`.
- Requer Docker CLI e acesso ao projeto Compose dentro do container.
- Hoje o container monta apenas o socket, entao pode exigir adicionar Docker CLI na imagem e montar o diretory do projeto, o que aumenta acoplamento.

#### Opcao B: Docker Engine API Pelo Socket

- O `legendas-webui` usa a Docker API via `/var/run/docker.sock` para iniciar/parar o container `whisper-asr` existente.
- Evita depender de `docker compose` dentro do container.
- Precisa garantir que o container ja exista. Caso tenha sido removido, instruir o usuario a recriar com `docker compose create whisper-asr` ou `docker compose up -d whisper-asr` uma vez.

Recomendacao inicial: usar Opcao B para start/stop de container existente, porque o socket ja esta montado e o servico tem `container_name: whisper-asr`. Documentar que a primeira criacao do container continua sendo pelo host/Compose.

### Integracao Com Whisper-ASR

Implementar modulo novo, por exemplo `whisper_jobs.py` ou `transcription.py`:

- Fila dedicada para transcricao.
- Estado atual: arquivo, inicio, etapa, erro, progresso textual.
- Funcoes para start/stop do container.
- Healthcheck HTTP em `http://whisper-asr:9000` ou endpoint disponivel da imagem.
- Upload do arquivo de video para a API do Whisper-ASR e salvamento do SRT retornado.

Endpoints propostos:

```text
POST /api/whisper/trigger
POST /api/whisper/cancel
GET /api/whisper/jobs
```

Payload inicial:

```json
{
  "path": "series/Show/S01/episode.mkv"
}
```

### Saida De Arquivo

- Para video `/media/series/X/ep01.mkv`, salvar `/media/series/X/ep01.en.srt`.
- Escrever primeiro em arquivo temporario no mesmo diretorio, por exemplo `.ep01.en.srt.tmp`, e renomear ao final para evitar arquivo parcial.
- Depois de criar `.en.srt`, chamar `job_manager.add_job()` automaticamente pode ser opcional.
- Recomendacao inicial: apos Whisper concluir, oferecer botao `Traduzir agora` em vez de traduzir automaticamente. Isso reduz efeitos cascata em caso de transcricao ruim.

### UI

- Adicionar estado de Whisper em `Em Processamento` ou criar uma secao pequena `Transcricao`.
- Mostrar etapas: `subindo container`, `aguardando API`, `transcrevendo`, `salvando`, `parando container`, `concluido`.
- Desabilitar botoes de Whisper enquanto houver job ativo.

## Feature 3: Visualizador De Legendas Recentes

### Comportamento Desejado

- Na tabela `Legendas Recentes`, adicionar acao `Abrir` ou tornar o nome do arquivo clicavel.
- Abrir uma nova pagina, por exemplo `/subtitles/view?path=<relativo>`, em outra rota FastAPI.
- Mostrar conteudo do `.srt` com formatação legivel:
  - Cabecalho com nome, idioma, tamanho, data e caminho relativo.
  - Corpo com blocos de legenda: indice, timestamp e texto.
  - Fallback para texto bruto se parser simples falhar.
- Incluir link para voltar ao dashboard.

### Implementacao Recomendada

Adicionar em `main.py`:

```text
GET /subtitles/view?path=<path-relativo>
GET /api/subtitles/read?path=<path-relativo>
```

Criar template novo:

```text
scripts/webui-legendas/templates/subtitle_view.html
```

Criar parser simples em modulo novo ou em `scanner.py`:

- Ler somente arquivos `.srt` dentro de `MEDIA_DIR`.
- Limitar tamanho maximo lido, por exemplo 2MB, para evitar travar a UI.
- Decodificar com `utf-8-sig` e fallback `latin-1` se necessario.
- Parsear blocos separados por linha em branco.
- Escapar HTML no template.

### Segurança

- Rejeitar path com traversal (`..`) ou symlink que resolva fora de `MEDIA_DIR`.
- Aceitar apenas extensao `.srt` na primeira versao.
- Nao permitir edicao ou download nesta fase.

## Modelo De Dados E Estado

Nao e necessario criar tabelas novas para a primeira versao de busca e visualizacao.

Para Whisper, existem duas opcoes:

- Estado em memoria apenas: suficiente para primeira versao, mas perde historico ao reiniciar.
- Persistir em SQLite como os jobs de traducao: melhor se quiser historico e recuperacao.

Recomendacao inicial: estado em memoria para Whisper, com historico curto em memoria, porque a acao e manual e longa. Se a feature virar uso frequente, migrar para SQLite usando padrao semelhante a `jobs.py`.

## Arquivos Provavelmente Alterados

- `scripts/webui-legendas/main.py`: novos endpoints de busca, detalhes, Whisper e visualizador.
- `scripts/webui-legendas/scanner.py`: busca global, resumo de arquivos e detalhes de video.
- `scripts/webui-legendas/templates/index.html`: campo de busca, resultados, botoes e links de visualizacao.
- `scripts/webui-legendas/templates/subtitle_view.html`: nova pagina de visualizacao.
- `scripts/webui-legendas/docker_utils.py`: start/stop/status do container `whisper-asr` via Docker API ou comandos seguros.
- `scripts/webui-legendas/transcription.py`: fila e execucao do Whisper, se separado.
- `scripts/webui-legendas/config.py`: novas constantes, timeouts e limites.
- `scripts/webui-legendas/requirements.txt`: adicionar dependencia somente se a Docker API for acessada por biblioteca Python; preferir stdlib HTTP sobre socket se ficar simples.
- `README.md` e `.env.example`: documentar variaveis novas caso sejam adicionadas.

## Variaveis Possiveis

Adicionar apenas se forem realmente usadas:

```dotenv
WHISPER_CONTAINER=whisper-asr
WHISPER_URL=http://whisper-asr:9000
WHISPER_START_TIMEOUT=180
WHISPER_TRANSCRIBE_TIMEOUT=7200
SUBTITLE_VIEW_MAX_BYTES=2097152
SEARCH_MIN_CHARS=2
SEARCH_LIMIT=50
```

## Fases De Implementacao

### Fase 1: Visualizador E Links

- Adicionar path relativo seguro nos itens de `get_recent_srt()`.
- Criar rota `/subtitles/view` e template `subtitle_view.html`.
- Adicionar botao/link `Abrir` na lista de legendas recentes.
- Validar leitura somente de `.srt` dentro de `MEDIA_DIR`.

Motivo: entrega valor rapido, baixo risco e cria utilitarios de path seguro reutilizaveis.

### Fase 2: Busca Global Leve

- Implementar `/api/search` com varredura textual e limite.
- Adicionar campo de busca com debounce no dashboard.
- Retornar videos e legendas com metadados baratos.
- Permitir `Visualizar` e `Traduzir` diretamente dos resultados.

### Fase 3: Detalhes Sob Demanda

- Implementar `/api/media/details`.
- Carregar legendas externas relacionadas e streams embutidos via `ffprobe` apenas ao expandir resultado.
- Exibir acoes por fonte: traduzir externa, traduzir embutida, visualizar SRT, gerar EN via Whisper.

### Fase 4: Whisper Manual On-Demand

- Implementar fila dedicada de transcricao.
- Implementar start/stop seguro de `whisper-asr`.
- Integrar chamada HTTP ao Whisper-ASR.
- Salvar `.en.srt` atomicamente.
- Exibir progresso e erros na UI.

### Fase 5: Refinamento

- Adicionar cache de busca se necessario.
- Persistir historico de Whisper em SQLite se o uso justificar.
- Adicionar confirmacao/regeneracao controlada para `.en.srt` existente.
- Avaliar backend `whisper.cpp` depois que o fluxo manual estiver estavel.

## Criterios De Sucesso

- A busca encontra videos e legendas fora da lista de candidatos pendentes.
- Digitar na busca nao dispara `ffprobe` para cada resultado.
- Detalhes de video mostram legendas externas e streams embutidos quando solicitados.
- O botao de Whisper sobe o container apenas quando necessario e libera RAM ao terminar.
- Whisper nunca sobrescreve `.en.srt` existente sem confirmacao.
- Arquivos gerados continuam com ownership compativel com `PUID:PGID`.
- A lista de legendas recentes abre uma pagina de visualizacao segura e legivel.
- `docker compose config >/dev/null` continua passando apos qualquer mudanca de Compose.
- `docker compose up -d --build legendas-webui` recria a Web UI sem erros.

## Riscos E Pontos Em Aberto

- A API exata do `onerahmet/openai-whisper-asr-webservice` precisa ser confirmada antes de implementar upload e formato de resposta SRT.
- Start/stop via Docker API exige testar permissao real do socket dentro do `legendas-webui`.
- Se o container `whisper-asr` nao existir porque nunca foi criado, a UI deve orientar a recriacao pelo host.
- Transcrever arquivo grande por upload pode consumir I/O e memoria; se ficar ruim, avaliar montar `./media:/media:ro` no `whisper-asr` e usar backend que aceite path local.
- Cancelamento de Whisper pode nao interromper a transcricao dentro do container se a API nao suportar cancelamento; nesse caso, cancelar deve marcar job e parar container apenas com confirmacao ou regra clara.
