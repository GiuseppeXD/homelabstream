# Homelab Jellyfin + qBittorrent + Prowlarr + Bazarr Stack

A minimal Docker Compose stack to self-host Jellyfin, qBittorrent, Prowlarr, and Bazarr on your local network, with FlareSolverr solving Cloudflare/JS challenges for stubborn indexers. The stack keeps configuration/state on disk so you can iterate safely while testing other homelab services later.

## Prerequisites

- Linux host with Docker Engine and Docker Compose plugin (`docker compose` command).
- Local storage for media (e.g., `/srv/media` or an external disk) that can be bind-mounted.
- Only download and share torrents that are legal in your jurisdiction (Linux ISOs, public-domain content, etc.).
- Allow outbound HTTP/HTTPS traffic so FlareSolverr can solve Cloudflare challenges for protected indexers.
- (Optional) VPN/proxy credentials if you later reintroduce a tunnel container such as Gluetun.

## Files

- `docker-compose.yml` – Defines Jellyfin, qBittorrent, Radarr, Sonarr, Prowlarr, Bazarr, and FlareSolverr containers, persistent volumes, and published ports.
- `.env.example` – Template for environment variables; copy to `.env` and adjust for your system.
- `config/qbittorrent` – qBittorrent settings and torrents.
- `config/jellyfin` – Jellyfin configuration, metadata, and user database.
- `config/radarr` – Radarr configuration/database.
- `config/sonarr` – Sonarr configuration/database.
- `config/prowlarr` – Prowlarr configuration, indexers, and logs.
- `config/bazarr` – Bazarr configuration and subtitle cache.
- `media/` – Placeholder mount for libraries and downloads. Replace with bind mounts to your actual media paths if desired.

## Setup

1. **Clone / copy this repo** onto the host that will run your media stack.
2. **Prepare env vars**:
   ```bash
   cp .env.example .env
   # edit .env with your preferred editor (adjust PUID/PGID/TZ and override service ports if you need)
   ```
   - `PUID`/`PGID`: match the UID/GID that should own the media data (typically your Linux user).
   - `TZ`: time zone string (e.g., `America/Sao_Paulo`).
   - `QBITTORRENT_WEBUI_PORT`: host port for the qBittorrent Web UI (default 8080).
   - `PROWLARR_PORT`: host port for Prowlarr (default 9696).
   - `BAZARR_PORT`: host port for Bazarr (default 6767).
   - `FLARESOLVERR_PORT`: host port for FlareSolverr’s API (default 8191).
   - `RADARR_PORT`: host port for Radarr (default 7878).
   - `SONARR_PORT`: host port for Sonarr (default 8989).
   - **Optional dedicated service account**:
     ```bash
     sudo groupadd -r homelab
     sudo useradd -r -m -g homelab -s /usr/sbin/nologin homelab
     id homelab   # copy UID -> PUID and GID -> PGID into .env
     sudo chown -R homelab:homelab config media
     ```
     This keeps container-owned files separated from your personal account.
3. **Create bind mount directories** (adjust paths if you want to use storage outside the repo):
   ```bash
   mkdir -p config/{qbittorrent,jellyfin,radarr,sonarr,prowlarr,bazarr}
   mkdir -p media/{movies,tv,transcode,downloads/completed,downloads/incomplete}
   ```
   - Replace `./media` with actual host paths by editing `docker-compose.yml` if your media already lives elsewhere.
4. **Launch the stack**:
   ```bash
   docker compose up -d
   ```
5. **Initial Jellyfin configuration**:
   - Go to `http://<host-ip>:8096` (HTTPS optional on `8920` once you add a cert).
   - Follow the Jellyfin wizard to create an admin user, choose metadata language, and add libraries pointing at `/media/movies`, `/media/tv`, or `/media/downloads/completed`.
   - Optional: enable hardware transcoding from the admin dashboard if your host supports it.
6. **Initial qBittorrent configuration**:
   - Run `docker compose logs qbittorrent | grep -i password` to grab the random password the LinuxServer image prints on first boot, then browse to `http://<host-ip>:<QBITTORRENT_WEBUI_PORT>` (default `8080`), login with `admin` / `<generated password>`, and change it immediately.
   - Open **Tools → Options → Downloads** and set:
     - Default save path: `/downloads/completed`
     - Keep incomplete torrents in: `/downloads/incomplete`
   - Optionally enable the Web UI to require HTTPS or limit IP ranges.
   - Add RSS feeds or indexers, or integrate with automation tools by pointing them to `http://qbittorrent:8080` on the internal Docker network (`media_net`)—the container always listens on 8080 internally even if you remap the host port.
7. **Initial Radarr configuration**:
   - Browse to `http://<host-ip>:<RADARR_PORT>`, run the first-run wizard, and set the root folders to `/media/movies` (or whichever subdirectory holds movies) plus the download folder `/downloads` for import.
   - Under **Settings → Download Clients**, add qBittorrent with `http://qbittorrent:8080` and the credentials you chose earlier.
   - Set quality profiles, lists, and root folders so Radarr can rename/move movies out of `/downloads` into `/media/movies`.
8. **Initial Sonarr configuration**:
   - Go to `http://<host-ip>:<SONARR_PORT>`, run the wizard, set root folders to `/media/tv`, and point the download folder to `/downloads`.
   - Add qBittorrent as a download client (same internal URL/credentials as above).
   - Create quality profiles, language preferences, and (optionally) connect to Trakt/Lists so Sonarr monitors the series you care about.
9. **Initial Prowlarr configuration (with FlareSolverr)**:
   - Visit `http://<host-ip>:<PROWLARR_PORT>`.
   - Create an admin password, then add your preferred indexers.
   - This compose file pins both Prowlarr’s and FlareSolverr’s DNS to Cloudflare (`1.1.1.1`/`1.0.0.1`) so stubborn trackers resolve correctly; adjust the `dns:` sections if your network needs different resolvers.
   - Add qBittorrent as a download client using the internal address `http://qbittorrent:8080` and the credentials you set above.
   - Under **Applications**, add Radarr and Sonarr (use `http://radarr:7878` / `http://sonarr:8989`) so Prowlarr can sync indexers to them automatically.
   - If an indexer returns Cloudflare/JavaScript challenges, add FlareSolverr under **Settings → Indexers → Add indexer → FlareSolverr** with `http://flaresolverr:8191`, then assign that solver to the affected indexers.
10. **Initial Bazarr configuration**:
   - Open `http://<host-ip>:<BAZARR_PORT>`, create an API key/password.
   - Under **Settings → Services** add Jellyfin via the internal URL `http://jellyfin:8096`, and qBittorrent (optional) via `http://qbittorrent:8080` to let Bazarr track download status.
   - Choose subtitle languages and point Bazarr’s paths to `/media/movies` and `/media/tv` so downloaded subtitles land next to your files.

## Maintenance

- Update images: `docker compose pull && docker compose up -d`.
- View logs: `docker compose logs -f flaresolverr`, `docker compose logs -f jellyfin`, `docker compose logs -f qbittorrent`, `docker compose logs -f radarr`, `docker compose logs -f sonarr`, `docker compose logs -f prowlarr`, `docker compose logs -f bazarr`.
- Stop the stack: `docker compose down` (data persists because it lives in `config/` and `media/`).

## Extending The Homelab

This compose project already defines an isolated bridge network (`media_net`). Additional services (e.g., Sonarr/Radarr/Lidarr, Traefik) can be added later by attaching them to the same network to share media mounts or reverse proxy access. Automation tools can drop completed downloads into `/downloads/completed`, which Jellyfin (via `/media`) already monitors, so libraries stay in sync automatically while Prowlarr/Bazarr handle discovery and subtitles.
