# Plano de Upgrade de Serviços Docker

> Gerado em: 2026-04-28
> Aplica-se a: `/home/gluca/homelabs/docker-compose.yml`

---

## Legenda

| Ícone | Significado |
|-------|-------------|
| 🔴 | Upgrade urgente (security/stability) |
| 🟡 | Upgrade recomendado (novas features/bugfixes) |
| 🟢 | Já na última versão |
| ⏸️ | Aguardar análise (risco de breaking change) |
| ⬆️ | Instrução de upgrade |

---

## Resumo Executivo

| Serviço | Atual | Última Stable | Status | Risco |
|---------|-------|---------------|--------|-------|
| flaresolverr | v3.4.6 | v3.4.6 | 🟢 | Baixo |
| qbittorrent | 5.1.4-r1-ls432 | 5.1.4-r3 | 🔴 | Baixo |
| radarr | 6.0.4.10291-ls289 | 6.1.1.10360-ls298 | 🟡 | Baixo |
| sonarr | 4.0.16.2944-ls300 | 4.0.17.2952-ls305 | 🔴 | Baixo |
| prowlarr | 2.3.0.5236-ls134 | 2.3.0.5236-ls139 | 🔴 | Baixo |
| bazarr | v1.5.3-ls328 | v1.5.6 | 🔴 | Baixo |
| jellyfin | 10.11.5ubu2404-ls13 | 10.11.8ubu2404-ls26 | 🔴 | Baixo |
| jellyseerr | 2.7.3 | 3.2.0 | ⏸️ | Alto |
| whisper-asr | v1.9.1 | v1.9.1 | 🟢 | — |
| ollama | ~v0.6.x | v0.22.1-rc0 | ⏸️ | Médio |
| python:3.12-slim (webui) | pinned | 3.12.13 | 🟡 | Baixo |

---

## 🔴 Upgrades Urgentes (Sem Breaking Changes)

### 1. qbittorrent: `5.1.4-r1-ls432` → `5.1.4-r3`
- **Motivo:** Security patches e bug fixes de libtorrent
- **Ação:** Atualizar digest SHA no docker-compose.yml
- **Preparação:** Backup de `./config/qbittorrent`
- **Rollback:** `docker compose down && restaurar SHA anterior`

### 2. sonarr: `4.0.16.2944-ls300` → `4.0.17.2952-ls305`
- **Motivo:** Bug fixes no parser de releases
- **Ação:** Atualizar digest SHA
- **Preparação:** Nenhuma — config compatível

### 3. prowlarr: `2.3.0.5236-ls134` → `2.3.0.5236-ls139`
- **Motivo:** Alpine base image rebase (security updates)
- **Ação:** Atualizar digest SHA
- **Preparação:** Nenhuma

### 4. bazarr: `v1.5.3-ls328` → `v1.5.6`
- **Motivo:** 3 minor releases com fixes críticos no jobs manager (deadlock, race conditions, high CPU busy-wait). O v1.5.3 tem bug conhecido que trava o processo principal.
- **Ação:** Atualizar digest SHA
- **Preparação:** Backup de `./config/bazarr`

### 5. jellyfin: `10.11.5ubu2404-ls13` → `10.11.8ubu2404-ls26`
- **Motivo:** 3 patches de bugfix e security (10.11.5 → 10.11.8)
- **Ação:** Atualizar digest SHA
- **Preparação:** Backup de `./config/jellyfin`
- **Nota:** Jellyfin 10.11.x é stable branch, upgrades patch são seguros

---

## 🟡 Upgrades Recomendados

### 6. radarr: `6.0.4.10291-ls289` → `6.1.1.10360-ls298`
- **Motivo:** Minor version bump (6.0 → 6.1) com novas features
- **Ação:** Atualizar digest SHA
- **Preparação:** Nenhuma — mesma major version
- **Rollback:** Reverter SHA se necessário

### 7. python:3.12-slim (legendas-webui base image)
- **Motivo:** Security patches da base Debian/Trixie
- **Ação:** Rebuild do container com novo digest
- **Preparação:** Nenhuma — app é stateless

---

## 🟢 Já na Última Versão

### 8. flaresolverr
- v3.4.6 é a última release disponível
- Nenhuma ação necessária

### 9. whisper-asr
- v1.9.1 é a última release disponível
- Nenhuma ação necessária

---

## ⏸️ Upgrades que Precisam de Análise

### 10. jellyseerr: `2.7.3` → `3.2.0` ⚠️ MAJOR
- **Breaking changes confirmados:**
  - Projeto renomeado de `jellyseerr` para **`seerr`** (novo namespace)
  - Possível mudança de imagem Docker (`fallenbagel/jellyseerr` → `seerrteam/seerr` ou `ghcr.io/seerr-team/seerr`)
  - Novas variáveis de ambiente: `COMMIT_TAG`, custom DNS
- **Risco:** Alto — pode quebrar integração com Jellyfin
- **Recomendação:**
  - Ler changelog de migração oficial antes de executar
  - Testar em ambiente separado se possível
  - Verificar compatibilidade com Jellyfin 10.11.x
- **Ação:** Aguardar estabilização da v3.x ou migração guiada

### 11. ollama: ~v0.6.x → v0.22.1-rc0 ⚠️
- **Gap enorme:** Pulou de v0.6 para v0.22 (muitas releases intermediárias)
- **Mudanças significativas:**
  - Novo engine Ollama (rewrite)
  - Suporte a modelos multimodais (visão)
  - Flash attention default para vision models
  - Batch inference support
  - Nova variável: `OLLAMA_CONTEXT_LENGTH`
- **Nossa API:** Usamos apenas POST `/api/generate` — provavelmente compatível
- **Risco:** Médio — pode afetar performance do qwen2.5:7b
- **Recomendação:**
  - Testar novo ollama isoladamente com o modelo atual
  - Verificar se `num_predict` ainda funciona
  - Fazer backup de `./config/ollama`
- **Ação:** Upgrade controlado com teste de tradução

---

## Checklist de Execução

### Fase 1 — Low Risk (🔴🟡)
- [ ] Backup: `tar czf homelabs-backup-$(date +%Y%m%d).tar.gz config/ docker-compose.yml`
- [ ] Atualizar digests SHA dos serviços 🔴🟡 no docker-compose.yml
- [ ] `docker compose pull`
- [ ] `docker compose up -d`
- [ ] Verificar logs: `docker compose logs -f`
- [ ] Testar acessos (UI das aplicações)

### Fase 2 — Medium Risk (ollama)
- [ ] Backup `./config/ollama`
- [ ] Identificar digest SHA da versão ollama desejada
- [ ] Atualizar docker-compose.yml
- [ ] Recriar container: `docker compose up -d ollama`
- [ ] Testar tradução via script manual:
  ```bash
  python3 scripts/translate-srt-ollama.py /path/to/test.en.srt /tmp/test.pt-BR.srt qwen2.5:7b "Brazilian Portuguese"
  ```
- [ ] Se falhar: rollback para SHA anterior

### Fase 3 — High Risk (jellyseerr) — FUTURO
- [ ] Ler documentação de migração oficial
- [ ] Identificar nova imagem Docker correta
- [ ] Verificar compatibilidade com Jellyfin
- [ ] Planejar migração de dados (`./config/jellyseerr` → novo path?)
- [ ] Executar em horário de baixo uso

---

## Referências

| Serviço | Changelog/Releases |
|---------|-------------------|
| flaresolverr | https://github.com/FlareSolverr/FlareSolverr/releases |
| linuxserver images | https://github.com/linuxserver?q=docker-&type=all |
| jellyfin | https://github.com/linuxserver/docker-jellyfin/releases |
| jellyseerr/seerr | https://github.com/seerr-team/seerr/releases |
| whisper-asr | https://github.com/ahmetoner/whisper-asr-webservice/releases |
| ollama | https://github.com/ollama/ollama/releases |

---

## Notas

- Todas as imagens LinuxServer são rebases de Alpine Linux — priorizar por security patches
- `lsXXX` no tag indica build number do LinuxServer CI
- Para serviços stateless (webui), rebuild é suficiente
- Para serviços com estado (jellyfin, bazarr, ollama), sempre fazer backup antes
