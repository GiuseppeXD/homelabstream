# Plano de Melhoria de Indexadores — Prowlarr/Sonarr

> Gerado em: 2026-04-28
> Aplica-se a: Prowlarr (`:9696`) e Sonarr (`:8989`)

---

## Estado Atual

**Prowlarr:** 30 indexadores configurados  
**Sonarr:** 13 indexadores sincronizados via Prowlarr  
**Tipo de série Jojo:** `Standard` (❌ deve ser `Anime`)  
**Anime Standard Format Search:** `true` ✅ nos indexadores Nyaa/SubsPlease

### Indexadores atuais relevantes para anime
| Nome | Tipo | Notas |
|------|------|-------|
| Nyaa.si | Público | Principal fonte de anime torrent |
| SubsPlease | Público | Rips de Crunchyroll com MultiSub |
| Shana Project | Público | Agregador de anime |
| ACG.RIP | Público | Chinês — pouco útil para PT-BR |
| dmhy | Público | Chinês |
| Mikan | Público | Chinês |
| Frozen Layer | Público | Espanhol — ocasionalmente útil |

---

## Parte 1 — Indexadores Públicos a Adicionar (Sem Convite)

### Fase 1: Anime (Prioridade Alta)

| Indexador | URL Base | Categoria | Motivo |
|-----------|----------|-----------|--------|
| **Anidex** | `https://anidex.info` | Anime (5070) | Focado em fansubs em inglês; grupos que não postam no Nyaa |
| **AniSource** | `https://asnet.pw` | Anime (5070) | HD raws de anime; útil para releases sem fansub |
| **AnimeTosho** | `https://animetosho.org` | Anime (5070) | Espelho do Nyaa + outras fontes; recupera torrents caídos |
| **Tokyo Toshokan** | `https://www.tokyotosho.info` | Anime (5070) | Tracker antigo; alguns releases exclusivos |

### Fase 2: Séries Gerais / Complementares (Prioridade Média)

| Indexador | URL Base | Categoria | Motivo |
|-----------|----------|-----------|--------|
| **1337x** | `https://1337x.to` | TV (5000) | Excelente para séries mainstream; muitos seeders |
| **TorrentGalaxy** | `https://torrentgalaxy.to` | TV (5000) | Alternativa ao RARBG; séries e filmes |
| **LimeTorrents** | `https://www.limetorrents.lol` | TV (5000) | Indexador geral com bom conteúdo |

### Como adicionar no Prowlarr

1. Abrir Prowlarr Web UI → `http://localhost:9696`
2. **Settings → Indexers → Add**
3. Selecionar o indexer na lista (ex: `Nyaa.si` clone → `Anidex`)
4. Categorias: marcar **Anime (5070)**
5. **Test** → **Save**
6. O sync automático envia para Sonarr em segundos

### Configurações recomendadas por indexer

```yaml
# Anidex, AniSource, AnimeTosho, Tokyo Toshokan
Anime Categories: [5070]  # Anime
Anime Standard Format Search: true  # Buscar tanto S01E01 quanto episódio 01
Minimum Seeders: 1
Priority: 25

# 1337x, TorrentGalaxy, LimeTorrents
Categories: [5000]  # TV
Minimum Seeders: 1
Priority: 25
```

---

## Parte 2 — Configurações no Sonarr

### Passo 1: Alterar Series Type para "Anime"

**Por quê:** Séries marcadas como `Standard` usam busca `S01E01`. Animes no Nyaa usam absolute numbering (`Episódio 01`). O Sonarr precisa do tipo `Anime` para buscar corretamente.

**Como fazer:**
1. Sonarr → **Series → Jojo's Bizarre Adventure**
2. **Edit → Series Type: Anime**
3. Save

**Efeito:** O Sonarr passa a buscar por:
- `Jojo's Bizarre Adventure 01` (absolute)
- `Jojo's Bizarre Adventure S04E01` (standard fallback, se `animeStandardFormatSearch: true`)

### Passo 2: Criar Release Profile para PT-BR / MultiSub

**Settings → Profiles → Release Profiles → Add**

| Campo | Valor |
|-------|-------|
| Name | `Anime PT-BR / MultiSub` |
| Must Contain | `MultiSub`, `pt-BR`, `Portuguese`, `BRA`, `BR` |
| Preferred (regex) | `1080p`, `BluRay`, `WEB-DL`, `NF`, `CR` |
| Cutoff | `WEB-DL-1080p` |
| Tags | `anime` |

**Aplicar:** Editar cada série de anime → Tags → `anime`

### Passo 3: Verificar XEM Aliases

O Sonarr usa `https://thexem.info` para mapear títulos alternativos de anime.

**Como verificar:**
1. Acessar `https://thexem.info/xem/show/3413` (Jojo Golden Wind)
2. Confirmar que os aliases estão corretos
3. Se faltar algum alias, reportar no Discord do Sonarr

---

## Parte 3 — Indexadores Privados (Requer Convite)

### O que são indexadores privados

 trackers fechados com comunidade curada. Vantagens:
- Qualidade superior (remuxes, BDMVs)
- Seeders dedicados (long-term retention)
- Conteúdo exclusivo (releases que nunca saem para público)
- Regras rigorosas de encode (consistência de qualidade)

### Principais indexadores privados de anime

| Nome | Tipo | Conteúdo | Dificuldade de acesso |
|------|------|----------|----------------------|
| **AnimeBytes (AB)** | Tracker | Anime, manga, OST, BDMVs | ⭐⭐⭐⭐⭐ Muito difícil |
| **BakaBT (BBT)** | Tracker | Anime clássico, remuxes | ⭐⭐⭐⭐ Difícil |
| **AnimeTorrents (AnimeZ)** | Tracker | Anime geral | ⭐⭐⭐ Moderado |
| **JPTV.club** | Tracker | TV japonesa, anime, doramas | ⭐⭐⭐ Moderado |
| **AnimeBytes** | Tracker | O maior do mundo | ⭐⭐⭐⭐⭐ Fechado |

### Como conseguir convite

#### AnimeBytes (AB)
- **Status:** Fechado para convites públicos há anos
- **Como entrar:**
  1. **Rastrear threads no Reddit:** `r/invites`, `r/trackers`
  2. **Fazer parte de trackers menores:** AB ocasionalmente abre para usuários de BakaBT, AnimeTorrents, RED (Redacted)
  3. **IRC:** `#animebytes` no `irc.rizon.net` — algumas vezes oficiais respondem
  4. **Conhecer alguém:** AB é ratio-based; membros precisam manter ratio para ganhar invites
- **Requisitos típicos:**
  - 6+ meses em outro tracker respeitável
  - Ratio > 1.0 comprovado
  - Perfil do invite forum limpo

#### BakaBT (BBT)
- **Status:** Aberto ocasionalmente
- **Como entrar:**
  1. **Site oficial:** `bakabt.me` — clique em "Sign Up" e veja se está aberto
  2. **IRC:** `#BakaBT` no `irc.rizon.net`
  3. **Reddit:** `r/BakaBT` — threads de convite ocasionais
- **Requisitos:**
  - Conta antiga em fóruns de anime (MyAnimeList, AniList, etc.)
  - Capacidade de seedar (upload mínimo)

#### AnimeTorrents (AnimeZ)
- **Status:** Registro aberto intermitente
- **Como entrar:**
  1. Acessar `https://animetorrents.me` diretamente
  2. Se registro estiver fechado, aguardar janelas de abertura (comunicadas no site)
  3. IRC: `#animetorrents` no `irc.xertion.org`
- **Requisitos:**
  - E-mail válido
  - Ratio commitment

#### JPTV.club
- **Status:** Registro fechado, convites via IRC
- **Como entrar:**
  1. IRC: `#jptv-invite` no `irc.xertion.org`
  2. Precisa de ratio proof de outro tracker

### Estratégia de Progressão (Tracker Ladder)

```
Fase 1: Indexadores Públicos (hoje)
  └── Nyaa, Anidex, SubsPlease, AnimeTosho
         │
         ▼
Fase 2: Trackers Semi-Privados / Fácil
  └── AnimeTorrents (registro aberto)
         │
         ▼
Fase 3: Trackers Médios (requer convite)
  └── BakaBT (via IRC / Reddit)
         │
         ▼
Fase 4: Trackers Elite (muito difícil)
  └── AnimeBytes (via ladder de outros trackers)
```

### Dicas para conseguir convites

1. **Seja ativo na comunidade:**
   - Participe do Discord/IRC dos trackers que já tem acesso
   - Ajude outros usuários, reporte problemas
   - Contribua com uploads (rips, traduções, OSTs)

2. **Mantenha ratio impecável:**
   - Nunca delete torrents imediatamente
   - Use seedbox ou deixe PC ligado seedando
   - Ratio > 2.0 é considerado excelente

3. **Documente seus ratios:**
   - Screenshots da página de perfil de cada tracker
   - Prepare "ratio proofs" para mostrar ao pedir convite

4. **Acompanhe oportunidades:**
   - `r/OpenSignups` no Reddit — trackers abrindo registro
   - `r/Invites` — threads de troca/convite
   - Trackers anunciam aberturas no Twitter/X oficial

5. **NUNCA:**
   - Compre convites (ban permanente em quase todos os trackers)
   - Peça convites em público (DM apenas)
   - Menti sobre ratio ou experiência

---

## Parte 4 — Por que Netflix/Crunchyroll Não Aparecem Diretamente

### O problema

Indexadores torrent **não rastreiam conteúdo original** de plataformas de streaming. Eles rastreiam **releases de grupos** que:

- Ripam o vídeo do serviço de streaming
- Extraem as legendas embutidas
- Reencodem ou remuxam em containers compatíveis

### Grupos que ripam de streaming

| Grupo | Fonte | Tag típica | Onde encontrar |
|-------|-------|------------|----------------|
| **Erai-raws** | Crunchyroll | `[Erai-raws] ... [MultiSub]` | Nyaa, Erai site (feed) |
| **SubsPlease** | Crunchyroll | `[SubsPlease] ... (1080p)` | Nyaa, SubsPlease site |
| **NC-Raws** | Netflix/Bilibili | `[NC-Raws] ... [CHS]` | Nyaa |
| **Lilith-Raws** | Netflix/Bilibili | `[Lilith-Raws] ...` | Nyaa |
| **Yameii** | Funimation/CR | `[Yameii] ...` | Nyaa |
| **Judas** | Várias | `[Judas] ...` | Nyaa, 1337x |

### Tags de idioma nos releases

| Tag | Significado |
|-----|-------------|
| `[MultiSub]` | Múltiplas legendas (geralmente 8–12 idiomas) |
| `[us][br][mx][es][fr][de][it][ru]` | Legendas incluídas por código de país |
| `[pt-BR]` | Legendas em português do Brasil |
| `[Portuguese]` | Legendas em português (geral) |

**Nota:** Erai-raws e SubsPlease geralmente incluem PT-BR nas legendas embutidas, mas nem sempre indicam no título do torrent. É necessário baixar e verificar.

---

## Parte 5 — Checklist de Implementação

### Hoje (Públicos)
- [ ] Adicionar **Anidex** no Prowlarr (categoria 5070)
- [ ] Adicionar **AniSource** no Prowlarr (categoria 5070)
- [ ] Adicionar **AnimeTosho** no Prowlarr (categoria 5070)
- [ ] Adicionar **1337x** no Prowlarr (categoria 5000)
- [ ] Adicionar **TorrentGalaxy** no Prowlarr (categoria 5000)
- [ ] Testar todos os novos indexadores
- [ ] Forçar sync Prowlarr → Sonarr (Settings → Apps → Sonarr → Sync)
- [ ] Alterar **Jojo** (e outros animes) para **Series Type = Anime** no Sonarr
- [ ] Criar **Release Profile** "Anime PT-BR / MultiSub" no Sonarr
- [ ] Aplicar tag `anime` nas séries relevantes
- [ ] Testar busca interativa no Sonarr

### Esta semana (Configuração)
- [ ] Verificar XEM aliases para animes problemáticos
- [ ] Ajustar prioridades de indexadores (Nyaa = 1, Anidex = 2, etc.)
- [ ] Monitorar se novos episódios de Jojo são encontrados
- [ ] Verificar logs do Sonarr em busca de `Rejected` releases

### Este mês (Semi-privados)
- [ ] Tentar registro no **AnimeTorrents**
- [ ] Acompanhar `r/OpenSignups` para trackers de anime
- [ ] Entrar no IRC de BakaBT e pedir informações sobre convites

### Futuro (Privados)
- [ ] Manter ratio impecável em todos os trackers públicos/semiprivados
- [ ] Documentar ratio proofs (screenshots)
- [ ] Participar ativamente das comunidades
- [ ] Aguardar oportunidade para AnimeBytes

---

## Recursos Úteis

| Recurso | URL | Descrição |
|---------|-----|-----------|
| Prowlarr Supported Indexers | https://wiki.servarr.com/prowlarr/supported-indexers | Lista completa de indexadores |
| XEM (TheXEM) | https://thexem.info | Mapeamento de títulos de anime |
| Nyaa.si | https://nyaa.si | Principal tracker público de anime |
| OpenSignups Reddit | https://reddit.com/r/OpenSignups | Trackers com registro aberto |
| Invites Reddit | https://reddit.com/r/Invites | Troca de convites |
| TrackerStatus | https://trackerstatus.info | Status de trackers (up/down) |

---

## Notas

- **AnimeBytes** é considerado o "Holy Grail" de trackers de anime. Não desista se não conseguir imediatamente — é normal levar meses ou anos.
- **Ratio é rei:** Em trackers privados, manter um bom ratio é mais importante que ter muitos torrents. Seed sempre.
- **VPN/Seedbox:** Altamente recomendado para trackers privados. Muitos exigem IP fixo ou permitem apenas certos países.
- **Nunca compartilhe conta:** Account sharing = ban permanente em praticamente todos os trackers privados.
