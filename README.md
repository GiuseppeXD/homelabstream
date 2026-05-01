# Homelab Media Stack

Stack Docker Compose para Jellyfin, downloads, automacao de catalogo e pipeline local de legendas com Whisper-ASR e Ollama.

## Servicos

| Servico | Porta host padrao | Funcao |
| --- | ---: | --- |
| Jellyfin | `8096` / `8920` | Biblioteca e streaming de midia |
| qBittorrent | `8080`, `6881/tcp`, `6881/udp` | Cliente torrent |
| Radarr | `7878` | Automacao de filmes |
| Sonarr | `8989` | Automacao de series |
| Prowlarr | `9696` | Indexadores para Radarr/Sonarr |
| Bazarr | `6767` | Busca, sincronizacao e geracao de legendas |
| Jellyseerr | `5055` | Pedidos de filmes/series integrados ao Jellyfin |
| FlareSolverr | `8191` | Resolver desafios Cloudflare/JS de indexadores |
| Whisper-ASR | `9000` | API local de transcricao de audio para legenda |
| Ollama | `11434` | LLM local usado para traduzir legendas |
| legendas-webui | `8990` | Dashboard e fila de traducao EN -> PT-BR |

Todos os servicos ficam na rede bridge `media_net`. Use os nomes dos servicos para comunicacao interna, por exemplo `http://qbittorrent:8080`, `http://radarr:7878`, `http://sonarr:8989`, `http://ollama:11434` e `http://whisper-asr:9000`.

## Estrutura

- `docker-compose.yml`: define os servicos, imagens pinadas por digest, portas, rede, limites de recurso e volumes.
- `.env.example`: template das variaveis exigidas pelo Compose. Copie para `.env` e ajuste localmente.
- `config/`: dados persistentes dos containers. Esta pasta e ignorada pelo Git.
- `media/`: downloads e bibliotecas de filmes/series. Esta pasta e ignorada pelo Git.
- `scripts/webui-legendas/`: app Flask usado pelo servico `legendas-webui`.
- `scripts/translate-srt-ollama.py`: tradutor standalone de `.srt` via Ollama.
- `scripts/bazarr-translate-postprocess.sh`: fallback legado para post-processing do Bazarr. O fluxo principal atual e o watchdog/fila do `legendas-webui`.
- `scripts/monitor-legendas.sh`: monitor de terminal para Whisper, Ollama, Bazarr e arquivos `.srt` recentes.

## Setup Inicial

1. Copie o arquivo de ambiente:

```bash
cp .env.example .env
```

2. Ajuste `.env`:

```dotenv
PUID=961
PGID=961
TZ=America/Sao_Paulo
TRANSLATE_MODEL=qwen2.5:7b
```

`PUID` e `PGID` devem ser o UID/GID que vai possuir os volumes escritos pelos containers. Neste setup, os volumes principais estao sob ownership do usuario de servico `homelab:homelab` (`961:961`). Se usar outro usuario, ajuste `.env` e ownership juntos.

3. Crie os diretorios persistentes:

```bash
mkdir -p config/{qbittorrent,jellyfin,radarr,sonarr,prowlarr,bazarr,jellyseerr,whisper/cache,ollama}
mkdir -p media/{downloads,movies,series}
```

4. Aplique ownership nos volumes que usam `PUID`/`PGID`:

```bash
sudo chown -R 961:961 config/{qbittorrent,jellyfin,radarr,sonarr,prowlarr,bazarr,whisper,ollama} media
```

Se o usuario de servico for outro, substitua `961:961` por `$(id -u <usuario>):$(id -g <usuario>)`.

5. Garanta permissao especifica para Jellyseerr:

```bash
sudo chown -R 1000:1000 config/jellyseerr
```

O container do Jellyseerr nao usa `PUID`/`PGID` neste Compose e normalmente grava como UID/GID `1000:1000`.

6. Suba a stack:

```bash
docker compose up -d --build
```

7. Baixe o modelo de traducao no Ollama:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
```

Se `TRANSLATE_MODEL` for outro, puxe o mesmo modelo configurado no `.env`.

## Ownership E Volumes

Os volumes sao bind mounts locais, nao volumes nomeados do Docker. Isso facilita backup e manutencao, mas exige ownership correto no host.

| Caminho host | Caminho container | Escritor esperado |
| --- | --- | --- |
| `./config/qbittorrent` | `/config` | qBittorrent com `PUID:PGID` |
| `./media/downloads` | `/downloads` | qBittorrent com `PUID:PGID` |
| `./config/radarr` | `/config` | Radarr com `PUID:PGID` |
| `./config/sonarr` | `/config` | Sonarr com `PUID:PGID` |
| `./config/prowlarr` | `/config` | Prowlarr com `PUID:PGID` |
| `./config/bazarr` | `/config` | Bazarr com `PUID:PGID` |
| `./config/jellyfin` | `/config` | Jellyfin com `PUID:PGID` |
| `./media` | `/media` | Radarr, Sonarr, Bazarr, Jellyfin e `legendas-webui` |
| `./config/jellyseerr` | `/app/config` | Usuario da imagem Jellyseerr, normalmente `1000:1000` |
| `./config/whisper/cache` | `/root/.cache` | Whisper-ASR |
| `./config/ollama` | `/root/.ollama` | Ollama |
| `/var/run/docker.sock` | `/var/run/docker.sock:ro` | `legendas-webui`, somente leitura |

O `legendas-webui` roda explicitamente como `user: "${PUID}:${PGID}"`, por isso precisa conseguir escrever em `./media`. Ele tambem recebe `group_add: "968"` para acessar `/var/run/docker.sock`; se o GID do grupo `docker` do host for diferente, atualize esse valor no `docker-compose.yml`.

## Execucao

Subir ou recriar tudo:

```bash
docker compose up -d --build
```

Subir somente a Web UI apos alterar `scripts/webui-legendas/`:

```bash
docker compose up -d --build legendas-webui
```

Ver estado dos servicos:

```bash
docker compose ps
```

Ver logs:

```bash
docker compose logs -f bazarr
docker compose logs -f legendas-webui
docker compose logs -f whisper-asr
docker compose logs -f ollama
```

Atualizar imagens pinadas no Compose exige editar os digests em `docker-compose.yml`. Para baixar as imagens configuradas e recriar containers:

```bash
docker compose pull
docker compose up -d --build
```

Parar sem apagar dados:

```bash
docker compose down
```

## Configuracao Dos Servicos

### qBittorrent

- Acesse `http://<host>:8080`.
- Usuario inicial: `admin`.
- A senha inicial e impressa nos logs do container na primeira inicializacao.
- Configure downloads para `/downloads` ou subpastas de `/downloads`.
- Para integracoes internas, use `http://qbittorrent:8080`.

### Radarr E Sonarr

- Radarr: `http://<host>:7878`.
- Sonarr: `http://<host>:8989`.
- Configure qBittorrent como download client usando `qbittorrent:8080`.
- Configure root folders em `/media/movies` e `/media/series`.
- Garanta que imports e renames preservem arquivos dentro de `/media`, pois Jellyfin, Bazarr e `legendas-webui` enxergam esse mesmo mount.

### Prowlarr E FlareSolverr

- Prowlarr: `http://<host>:9696`.
- FlareSolverr interno: `http://flaresolverr:8191`.
- O Compose fixa DNS Cloudflare (`1.1.1.1` e `1.0.0.1`) nos servicos que acessam indexadores.
- Sincronize indexadores do Prowlarr para Radarr e Sonarr usando `http://radarr:7878` e `http://sonarr:8989`.

### Jellyfin E Jellyseerr

- Jellyfin: `http://<host>:8096`.
- Jellyseerr: `http://<host>:5055`.
- No Jellyfin, aponte bibliotecas para `/media/movies` e `/media/series`.
- No Jellyseerr, integre com Jellyfin, Radarr e Sonarr usando URLs internas da rede Compose.

### Bazarr, Whisper-ASR E Ollama

- Bazarr: `http://<host>:6767`.
- Whisper-ASR: `http://<host>:9000`.
- Ollama: `http://<host>:11434`.
- Configure Bazarr para trabalhar sobre `/media/movies` e `/media/series`.
- O Whisper-ASR usa `ASR_ENGINE=faster_whisper` e `ASR_MODEL=${WHISPER_MODEL:-large-v3}`.
- O Ollama usa `TRANSLATE_MODEL` para traducoes EN -> PT-BR, por padrao `qwen2.5:7b`.

## Pipeline De Legendas

1. Bazarr busca ou gera legendas em ingles, normalmente como `*.en.srt`, ao lado do arquivo de midia em `/media/movies` ou `/media/series`.
2. `legendas-webui` observa recursivamente `/media/movies` e `/media/series` com `watchdog`.
3. Quando um `*.en.srt` aparece ou e modificado, o arquivo entra em uma fila de traducao em memoria.
4. A Web UI chama a API do Ollama em `http://ollama:11434/api/generate`.
5. A traducao e salva ao lado do original como `*.pt-BR.srt`.
6. Se o `*.pt-BR.srt` ja existir, o job e ignorado para evitar sobrescrita.

Acesse o dashboard em `http://<host>:8990`. Ele mostra status de Whisper-ASR, Ollama, Bazarr, fila de traducao e legendas recentes. A aplicacao usa Docker CLI dentro do container para ler `docker stats`, `docker ps` e logs do Bazarr via socket Docker montado somente leitura.

Tambem e possivel monitorar via terminal:

```bash
./scripts/monitor-legendas.sh
```

Por padrao, esse script assume `MEDIA_DIR=/home/gluca/homelabs/media`. Override se rodar em outro caminho:

```bash
MEDIA_DIR=/caminho/para/media ./scripts/monitor-legendas.sh
```

## Validacao Rapida

```bash
docker compose config >/dev/null
docker compose ps
docker compose exec ollama ollama list
```

Para testar a traducao de um arquivo especifico:

```bash
docker compose exec -T legendas-webui python3 - <<'PY'
import requests
path = "/media/series/exemplo.en.srt"
print(requests.post("http://127.0.0.1:8989/api/translate/trigger", json={"path": path}).json())
PY
```

Substitua `path` por um arquivo real `*.en.srt` dentro de `/media/movies` ou `/media/series`.

## Backups

Faça backup de:

- `.env`, armazenado fora do Git.
- `config/`, com bancos e configuracoes dos apps.
- `media/`, se este repositorio tambem for o local real da biblioteca.

Nao versionar `config/`, `media/` ou `.env`; esses caminhos estao no `.gitignore` por conterem dados locais, midia, caches e possiveis tokens.
