# AGENTS.md

Orientacoes para agentes e contribuidores trabalhando neste repositorio.

## Contexto Do Projeto

Este repositorio opera uma stack Docker Compose de homelab/media. O arquivo principal e `docker-compose.yml`; os dados runtime ficam em bind mounts locais sob `config/` e `media/`, ambos ignorados pelo Git.

Servicos atuais:

- Jellyfin, qBittorrent, Radarr, Sonarr, Prowlarr, Bazarr, Jellyseerr e FlareSolverr.
- Whisper-ASR e Ollama para pipeline local de legendas.
- `legendas-webui`, app Flask em `scripts/webui-legendas/`, para dashboard e fila de traducao EN -> PT-BR.

## Regras De Seguranca

- Nao leia, imprima ou versione `.env`; use `.env.example` como referencia.
- Nao versione `config/` ou `media/`.
- Nao remova dados de runtime, arquivos de midia, torrents, bancos SQLite ou caches sem pedido explicito.
- Nao rode comandos destrutivos de Docker, como remover volumes, limpar imagens ou apagar containers, sem confirmacao explicita.
- Nao altere digests de imagens sem explicar o motivo e validar o Compose.

## Setup E Execucao

Validar Compose:

```bash
docker compose config >/dev/null
```

Subir a stack:

```bash
docker compose up -d --build
```

Rebuild somente da Web UI de legendas:

```bash
docker compose up -d --build legendas-webui
```

Checar estado:

```bash
docker compose ps
```

Logs mais uteis:

```bash
docker compose logs -f legendas-webui
docker compose logs -f bazarr
docker compose logs -f whisper-asr
docker compose logs -f ollama
```

## Ownership Dos Volumes

O setup usa bind mounts locais. A maior parte dos containers LinuxServer e o `legendas-webui` dependem de `PUID`/`PGID`.

- `config/qbittorrent`, `config/jellyfin`, `config/radarr`, `config/sonarr`, `config/prowlarr`, `config/bazarr`, `config/whisper`, `config/ollama` e `media/` devem ser gravaveis por `PUID:PGID`.
- Neste host, os volumes principais foram observados como `homelab:homelab` (`961:961`).
- `config/jellyseerr` e excecao: o Compose atual nao passa `PUID`/`PGID` para Jellyseerr; a imagem normalmente grava como `1000:1000`.
- `legendas-webui` roda com `user: "${PUID}:${PGID}"` e precisa escrever em `media/` para criar `*.pt-BR.srt`.
- `legendas-webui` usa `group_add: "968"` para acessar `/var/run/docker.sock`; se o GID do grupo `docker` mudar, atualize o Compose.

Comando de referencia para corrigir ownership dos volumes principais:

```bash
sudo chown -R 961:961 config/{qbittorrent,jellyfin,radarr,sonarr,prowlarr,bazarr,whisper,ollama} media
sudo chown -R 1000:1000 config/jellyseerr
```

Substitua `961:961` pelo `PUID:PGID` real caso o `.env` use outro usuario.

## Detalhes De Implementacao

- Todos os servicos usam a rede `media_net`.
- Para chamadas internas, use nomes de servico, nao `localhost`.
- `qBittorrent` escuta internamente em `8080`, mesmo que a porta host mude.
- `legendas-webui` expõe `8989` no container e `8990` no host.
- `legendas-webui` monta `/var/run/docker.sock` como somente leitura para consultar `docker ps`, `docker stats` e logs do Bazarr.
- O dashboard observa `/media/series` e `/media/movies` por arquivos `*.en.srt`.
- A traducao cria `*.pt-BR.srt` ao lado do arquivo original e nao sobrescreve se o destino ja existir.
- A fila de traducao do `legendas-webui` e em memoria; reiniciar o container limpa a fila pendente.
- `scripts/bazarr-translate-postprocess.sh` e fallback legado. O fluxo principal de traducao e feito pelo `legendas-webui`.

## Como Alterar

- Mudancas de orquestracao devem ficar em `docker-compose.yml` e `.env.example` quando criarem novas variaveis.
- Mudancas no dashboard ficam em `scripts/webui-legendas/app.py`, `templates/` e, se existir, `static/`.
- Se adicionar variavel de ambiente no Compose, documente no `README.md` e em `.env.example`.
- Se adicionar volume, documente o ownership esperado no `README.md` e neste arquivo.
- Prefira alteracoes pequenas e verificaveis.

## Validacao Antes De Finalizar

Para alteracoes em Compose ou documentacao de execucao:

```bash
docker compose config >/dev/null
```

Para alteracoes em `legendas-webui`:

```bash
docker compose up -d --build legendas-webui
docker compose logs --tail=50 legendas-webui
```

Para verificar modelo Ollama disponivel:

```bash
docker compose exec ollama ollama list
```

Nao faca commit automaticamente; apenas quando solicitado.
