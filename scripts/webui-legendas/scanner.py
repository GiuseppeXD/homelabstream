import os
import time
from datetime import datetime
from pathlib import Path

from config import (
    MEDIA_DIR, SCAN_INTERVAL, SCAN_MIN_AGE, AUTO_QUEUE_LIMIT,
    VIDEO_EXTENSIONS, SUBTITLE_EXTENSIONS, PT_LANGS, EN_LANGS, LANG_SUFFIXES,
)
from extractor import ffprobe_subtitles


candidate_cache = {"updated_at": 0, "items": [], "error": None}


def media_roots():
    return [os.path.join(MEDIA_DIR, "series"), os.path.join(MEDIA_DIR, "movies")]


def is_video(path):
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def is_subtitle(path):
    return Path(path).suffix.lower() in SUBTITLE_EXTENSIONS


def normalize_lang(value):
    if not value:
        return "unknown"
    value = str(value).lower().replace("_", "-")
    return LANG_SUFFIXES.get(value, value)


def is_ptbr_lang(lang):
    return normalize_lang(lang) in {"pt-BR", "pt"} or str(lang).lower() in PT_LANGS


def is_english_lang(lang):
    return normalize_lang(lang) == "en" or str(lang).lower() in EN_LANGS


def lang_from_subtitle_name(path):
    name = Path(path).name.lower()
    for suffix, lang in LANG_SUFFIXES.items():
        for ext in SUBTITLE_EXTENSIONS:
            if name.endswith(f".{suffix}{ext}"):
                return lang
    return "unknown"


def video_output_path(video_path):
    return str(Path(video_path).with_suffix("")) + ".pt-BR.srt"


def subtitle_output_path(subtitle_path):
    path = Path(subtitle_path)
    base = str(path.with_suffix(""))
    lowered = base.lower()
    for suffix in sorted(LANG_SUFFIXES, key=len, reverse=True):
        for marker in (f".embedded.{suffix}", f".{suffix}"):
            if lowered.endswith(marker):
                base = base[: -len(marker)]
                return base + ".pt-BR.srt"
    return base + ".pt-BR.srt"


def external_subtitles_for_video(video_path):
    video = Path(video_path)
    prefix = video.with_suffix("").name + "."
    results = []
    try:
        for item in video.parent.iterdir():
            if item.is_file() and item.suffix.lower() in SUBTITLE_EXTENSIONS and item.name.startswith(prefix):
                results.append(str(item))
    except OSError:
        pass
    return results


def external_ptbr_exists(video_path):
    return any(is_ptbr_lang(lang_from_subtitle_name(path)) for path in external_subtitles_for_video(video_path))


def stream_candidate(video_path, stream):
    tags = stream.get("tags") or {}
    title = tags.get("title", "")
    lang = normalize_lang(tags.get("language", "unknown"))
    forced = "forced" in title.lower() or "forc" in title.lower()
    codec = stream.get("codec_name", "unknown")
    score = 100 if is_english_lang(lang) else 70
    if forced:
        score -= 45
    return {
        "source_type": "embedded",
        "source": video_path,
        "video_path": video_path,
        "stream_index": stream.get("index"),
        "codec": codec,
        "language": lang,
        "title": title or f"stream {stream.get('index')}",
        "output": video_output_path(video_path),
        "filename": Path(video_path).name,
        "score": score,
        "reason": "Legenda inglesa embutida" if is_english_lang(lang) else "Legenda embutida em outro idioma",
    }


def external_candidate(path, video_path):
    lang = lang_from_subtitle_name(path)
    score = 90 if is_english_lang(lang) else 60
    return {
        "source_type": "external",
        "source": path,
        "video_path": video_path,
        "language": lang,
        "output": subtitle_output_path(path),
        "filename": Path(path).name,
        "score": score,
        "reason": "Legenda inglesa externa" if is_english_lang(lang) else "Legenda externa em outro idioma",
    }


def discover_candidates(limit=100):
    candidates = []
    now = time.time()
    for root in media_roots():
        if not os.path.exists(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                video_path = os.path.join(dirpath, filename)
                if not is_video(video_path):
                    continue
                try:
                    if now - os.path.getmtime(video_path) < SCAN_MIN_AGE:
                        continue
                except OSError:
                    continue

                if external_ptbr_exists(video_path) or os.path.exists(video_output_path(video_path)):
                    continue

                video_candidates = []
                for stream in ffprobe_subtitles(video_path):
                    lang = normalize_lang((stream.get("tags") or {}).get("language", "unknown"))
                    if is_ptbr_lang(lang):
                        video_candidates = []
                        break
                    video_candidates.append(stream_candidate(video_path, stream))
                else:
                    for subtitle in external_subtitles_for_video(video_path):
                        lang = lang_from_subtitle_name(subtitle)
                        if not is_ptbr_lang(lang):
                            video_candidates.append(external_candidate(subtitle, video_path))

                if video_candidates:
                    candidates.append(sorted(video_candidates, key=lambda item: item["score"], reverse=True)[0])

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


def refresh_candidates():
    global candidate_cache
    try:
        candidates = discover_candidates()
        candidate_cache.update({"updated_at": time.time(), "items": candidates, "error": None})
    except Exception as exc:
        candidate_cache.update({"updated_at": time.time(), "items": [], "error": str(exc)})
        print(f"subtitle scanner failed: {exc}")


def format_size(size):
    if size > 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}MB"
    if size > 1024:
        return f"{size / 1024:.0f}KB"
    return f"{size}B"


def format_elapsed(mtime):
    elapsed = time.time() - mtime
    if elapsed < 60:
        return f"{int(elapsed)}s"
    if elapsed < 3600:
        return f"{int(elapsed / 60)}m"
    if elapsed < 86400:
        return f"{int(elapsed / 3600)}h"
    return f"{int(elapsed / 86400)}d"


def get_recent_srt():
    files = []
    for root in media_roots():
        if not os.path.exists(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                path = os.path.join(dirpath, filename)
                if not filename.endswith(".srt"):
                    continue
                try:
                    mtime = os.path.getmtime(path)
                    if time.time() - mtime > 2880 * 60:
                        continue
                    size = os.path.getsize(path)
                except OSError:
                    continue
                lang = lang_from_subtitle_name(path)
                flag = "BR" if is_ptbr_lang(lang) else "US" if is_english_lang(lang) else "  "
                files.append({
                    "path": path,
                    "relpath": os.path.relpath(path, MEDIA_DIR),
                    "filename": filename,
                    "lang": lang,
                    "flag": flag,
                    "size": format_size(size),
                    "ago": format_elapsed(mtime),
                    "timestamp": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                })
    files.sort(key=lambda item: item["timestamp"], reverse=True)
    return files[:20]


def get_video_details(video_path):
    if not os.path.isfile(video_path) or not is_video(video_path):
        return None
    ext_subs = []
    for sub_path in external_subtitles_for_video(video_path):
        lang = lang_from_subtitle_name(sub_path)
        ext_subs.append({"path": sub_path, "lang": lang})
    embedded = []
    for stream in ffprobe_subtitles(video_path):
        tags = stream.get("tags") or {}
        lang = normalize_lang(tags.get("language", "unknown"))
        embedded.append({
            "index": stream.get("index"),
            "language": lang,
            "codec": stream.get("codec_name", "unknown"),
            "title": tags.get("title", ""),
        })
    return {
        "video_path": video_path,
        "filename": Path(video_path).name,
        "external_subtitles": ext_subs,
        "embedded_subtitles": embedded,
        "output_ptbr": video_output_path(video_path),
        "output_en": str(Path(video_path).with_suffix("")) + ".en.srt",
    }


def search_media(query, limit=50):
    if not query or len(query.strip()) < 2:
        return []
    q = query.lower().strip()
    results = []
    seen = set()
    for root in media_roots():
        if not os.path.exists(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if q not in filename.lower():
                    continue
                full = os.path.join(dirpath, filename)
                if full in seen:
                    continue
                seen.add(full)
                rel = os.path.relpath(full, MEDIA_DIR)
                ext = Path(filename).suffix.lower()
                if is_video(full):
                    kind = "video"
                elif is_subtitle(full):
                    kind = "subtitle"
                else:
                    continue
                entry = {
                    "path": full,
                    "relpath": rel,
                    "filename": filename,
                    "kind": kind,
                }
                if kind == "subtitle":
                    entry["lang"] = lang_from_subtitle_name(full)
                    entry["output"] = subtitle_output_path(full)
                    entry["output_exists"] = os.path.exists(entry["output"])
                if kind == "video":
                    entry["has_ptbr"] = os.path.exists(video_output_path(full))
                    entry["has_en"] = any(
                        is_english_lang(lang_from_subtitle_name(p))
                        for p in external_subtitles_for_video(full)
                    )
                results.append(entry)
                if len(results) >= limit:
                    return results
    return results


def scanner_loop(add_job_func):
    while True:
        refresh_candidates()
        queued = 0
        for candidate in candidate_cache["items"]:
            if queued >= AUTO_QUEUE_LIMIT:
                break
            if add_job_func(candidate):
                queued += 1
        time.sleep(SCAN_INTERVAL)
