from flask import Flask, render_template, jsonify, make_response, request
import json
import hashlib
import os
import queue
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import requests as req
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

app = Flask(__name__)

MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "5"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "qwen2.5:7b")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "40"))
NUM_PREDICT = int(os.getenv("NUM_PREDICT", "2048"))
SCAN_INTERVAL = int(os.getenv("SUBTITLE_SCAN_INTERVAL", "300"))
SCAN_MIN_AGE = int(os.getenv("SUBTITLE_SCAN_MIN_AGE", "600"))
AUTO_QUEUE_LIMIT = int(os.getenv("SUBTITLE_AUTO_QUEUE_LIMIT", "0"))

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa"}
PT_LANGS = {"pb", "pob", "pt-br", "pt_br", "por", "pt"}
EN_LANGS = {"en", "eng"}
LANG_SUFFIXES = {
    "en": "en",
    "eng": "en",
    "fr": "fr",
    "fre": "fr",
    "fra": "fr",
    "es": "es",
    "spa": "es",
    "ja": "ja",
    "jpn": "ja",
    "pb": "pt-BR",
    "pob": "pt-BR",
    "pt-br": "pt-BR",
    "pt_br": "pt-BR",
    "por": "pt",
    "pt": "pt",
}

candidate_cache = {"updated_at": 0, "items": [], "error": None}


def run_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        output = result.stdout.strip()
        if not output and result.stderr:
            output = result.stderr.strip()
        return output
    except Exception:
        return ""


def run_exec(args, timeout=60):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


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


def source_cache_path(job):
    cache_dir = Path("/tmp/legendas-webui")
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = Path(job["output"])
    lang = normalize_lang(job.get("language", "unknown"))
    source_type = job.get("source_type", "external")
    digest = hashlib.sha1(f"{job.get('source')}|{job.get('stream_index')}|{output}".encode()).hexdigest()[:12]
    return str(cache_dir / f"{output.stem}.{source_type}.{lang}.{digest}.srt")


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


def ffprobe_subtitles(video_path):
    try:
        result = run_exec([
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "s",
            "-show_entries",
            "stream=index,codec_name:stream_tags=language,title",
            "-of",
            "json",
            video_path,
        ], timeout=30)
        if result.returncode != 0:
            return []
        return json.loads(result.stdout or "{}").get("streams", [])
    except Exception as exc:
        print(f"ffprobe failed for {video_path}: {exc}")
        return []


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


class TranslationManager:
    def __init__(self):
        self.pending = queue.Queue()
        self.current = None
        self.current_start = None
        self.completed = []
        self._known_jobs = set()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cancelled = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _job_key(self, job):
        return f"{job.get('source')}|{job.get('stream_index')}|{job.get('output')}"

    def add_job(self, source, **kwargs):
        if isinstance(source, dict):
            job = dict(source)
        else:
            job = {"source": source, "source_type": "external"}
        job.update({k: v for k, v in kwargs.items() if v is not None})
        job.setdefault("source_type", "external")
        job.setdefault("language", lang_from_subtitle_name(job["source"]))
        job.setdefault("output", subtitle_output_path(job["source"]))
        job.setdefault("filename", os.path.basename(job["source"]))

        if not os.path.exists(job["source"]):
            return False
        if os.path.exists(job["output"]):
            return False
        if is_ptbr_lang(job.get("language")):
            return False

        key = self._job_key(job)
        with self._lock:
            if self.current and self._job_key(self.current) == key:
                return False
            if key in self._known_jobs:
                return False
            self._known_jobs.add(key)
        self.pending.put(job)
        return True

    def cancel_current(self):
        self._cancelled.set()

    def _worker(self):
        while not self._stop_event.is_set():
            try:
                job = self.pending.get(timeout=1)
            except queue.Empty:
                continue

            self._cancelled.clear()
            with self._lock:
                self.current = {**job, "status": "running"}
                self.current_start = time.time()

            try:
                success = self._process_job(job)
                if success:
                    self.completed.append({
                        **job,
                        "completed_at": datetime.now().strftime("%H:%M:%S"),
                    })
            except Exception as exc:
                print(f"Translation failed for {job.get('source')}: {exc}")
            finally:
                with self._lock:
                    self.current = None
                    self.current_start = None
                    self._known_jobs.discard(self._job_key(job))
                self.pending.task_done()

    def _process_job(self, job):
        source_srt = self._prepare_source(job)
        if not source_srt:
            return False
        return self._translate_srt(source_srt, job["output"], job.get("language", "unknown"))

    def _prepare_source(self, job):
        source = job["source"]
        source_type = job.get("source_type", "external")
        if source_type == "embedded":
            target = source_cache_path(job)
            result = run_exec([
                "ffmpeg",
                "-y",
                "-i",
                source,
                "-map",
                f"0:{job['stream_index']}",
                target,
            ], timeout=300)
            if result.returncode != 0:
                print(f"ffmpeg extract failed for {source}: {result.stderr[-1000:]}")
                return None
            return target

        suffix = Path(source).suffix.lower()
        if suffix == ".srt":
            return source

        target = source_cache_path(job)
        result = run_exec(["ffmpeg", "-y", "-i", source, target], timeout=120)
        if result.returncode != 0:
            print(f"ffmpeg convert failed for {source}: {result.stderr[-1000:]}")
            return None
        return target

    def _translate_srt(self, source_path, output_path, source_language):
        with open(source_path, "r", encoding="utf-8-sig") as handle:
            content = handle.read().replace("\r\n", "\n").replace("\r", "\n")

        entries = []
        for block in re.split(r"\n\s*\n", content.strip()):
            lines = block.strip().split("\n")
            if len(lines) >= 3 and lines[0].strip().isdigit():
                entries.append({
                    "seq": lines[0].strip(),
                    "timestamp": lines[1].strip(),
                    "text": "\n".join(lines[2:]),
                })
        if not entries:
            return False

        translated = []
        source_label = "English" if is_english_lang(source_language) else f"language code {source_language}"
        for i in range(0, len(entries), BATCH_SIZE):
            if self._cancelled.is_set():
                return False
            batch = entries[i : i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            prompt_lines = [
                f"Translate these subtitles from {source_label} to Brazilian Portuguese.",
                "Keep names, honorifics, tone, and line breaks where useful.",
                "Return ONLY numbered translated lines in the same order.",
            ]
            for n, entry in enumerate(batch, 1):
                prompt_lines.append(f"{n}. {entry['text']}")
            prompt = "\n".join(prompt_lines)

            try:
                response = req.post(OLLAMA_URL, json={
                    "model": TRANSLATE_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": NUM_PREDICT},
                }, timeout=300)
                response.raise_for_status()
                raw = response.json().get("response", "").strip()
                batch_translated = []
                for line in raw.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    match = re.match(r"^\d+[.)]\s*(.*)", line)
                    batch_translated.append(match.group(1) if match else line)
                if len(batch_translated) < len(batch):
                    batch_translated.extend(entry["text"] for entry in batch[len(batch_translated) :])
                elif len(batch_translated) > len(batch):
                    batch_translated = batch_translated[: len(batch)]
            except Exception as exc:
                print(f"Ollama batch {batch_num} failed: {exc}")
                batch_translated = [entry["text"] for entry in batch]

            for entry, text in zip(batch, batch_translated):
                translated.append({**entry, "text": text})

        with open(output_path, "w", encoding="utf-8") as handle:
            for i, entry in enumerate(translated):
                if i:
                    handle.write("\n\n")
                handle.write(f"{entry['seq']}\n{entry['timestamp']}\n{entry['text']}")
            handle.write("\n")
        return True

    def get_status(self):
        with self._lock:
            current_info = None
            if self.current and self.current_start:
                current_info = {
                    **self.current,
                    "elapsed": int(time.time() - self.current_start),
                    "status": "running",
                }
            return {
                "current": current_info,
                "pending_count": self.pending.qsize(),
                "pending": list(self.pending.queue),
                "completed": self.completed[-20:],
            }


translation_manager = TranslationManager()


class SubtitleWatcher(PatternMatchingEventHandler):
    def __init__(self, manager):
        super().__init__(patterns=["*.srt", "*.ass", "*.ssa"], ignore_directories=True)
        self.manager = manager

    def on_created(self, event):
        self._queue(event.src_path)

    def on_modified(self, event):
        self._queue(event.src_path)

    def _queue(self, path):
        if not is_subtitle(path):
            return
        lang = lang_from_subtitle_name(path)
        if is_ptbr_lang(lang):
            return
        self.manager.add_job(path, language=lang, output=subtitle_output_path(path))


observer = None


def start_watcher():
    global observer
    if observer is not None:
        return
    observer = Observer()
    for watch_dir in media_roots():
        if os.path.exists(watch_dir):
            observer.schedule(SubtitleWatcher(translation_manager), watch_dir, recursive=True)
            print(f"Watching {watch_dir}")
    observer.start()


def scanner_loop():
    while True:
        try:
            candidates = discover_candidates()
            candidate_cache.update({"updated_at": time.time(), "items": candidates, "error": None})
            queued = 0
            for candidate in candidates:
                if queued >= AUTO_QUEUE_LIMIT:
                    break
                if translation_manager.add_job(candidate):
                    queued += 1
        except Exception as exc:
            candidate_cache.update({"updated_at": time.time(), "items": [], "error": str(exc)})
            print(f"subtitle scanner failed: {exc}")
        time.sleep(SCAN_INTERVAL)


def start_scanner():
    thread = threading.Thread(target=scanner_loop, daemon=True)
    thread.start()


def get_container_stats(name):
    try:
        output = run_cmd(f"docker stats --no-stream {name}")
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 7:
                return {"cpu": parts[2], "mem_usage": parts[3] + " " + parts[4] + " " + parts[5], "mem_perc": parts[6]}
    except Exception:
        pass
    return {"cpu": "--", "mem_usage": "--", "mem_perc": "--"}


def get_container_status(name):
    output = run_cmd(f"docker ps --filter 'name={name}'")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) >= 2:
        parts = lines[1].split()
        for i, part in enumerate(parts):
            if part.startswith("Up") or part.startswith("Exited"):
                return " ".join(parts[i : i + 3]) if i + 3 <= len(parts) else part
    return "stopped"


def get_cpu_status(container, threshold):
    try:
        output = run_cmd(f"docker stats --no-stream {container}")
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if len(lines) >= 2:
            cpu_val = float(lines[1].split()[2].replace("%", ""))
            return "processing" if cpu_val > threshold else "idle"
    except Exception:
        pass
    return "unknown"


def get_ollama_models():
    models = run_cmd("docker exec ollama ollama list 2>/dev/null | tail -n +2 | awk '{print $1}'")
    return [model.strip() for model in models.split("\n") if model.strip()]


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
                flag = "🇧🇷" if is_ptbr_lang(lang) else "🇺🇸" if is_english_lang(lang) else "🌐"
                files.append({
                    "path": path,
                    "filename": filename,
                    "lang": lang,
                    "flag": flag,
                    "size": format_size(size),
                    "ago": format_elapsed(mtime),
                    "timestamp": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                })
    files.sort(key=lambda item: item["timestamp"], reverse=True)
    return files[:20]


def get_bazarr_activity():
    logs = run_cmd("docker logs --since 5m bazarr 2>/dev/null | grep -iE 'whisper|subtitle|download|processing' | tail -5")
    lines = [line.strip() for line in logs.split("\n") if line.strip()]
    return lines[-5:] if lines else ["No recent activity"]


@app.route("/")
def index():
    return render_template("index.html", refresh_interval=REFRESH_INTERVAL)


@app.route("/api/status")
def api_status():
    translation_status = translation_manager.get_status()
    current_processing = {}
    if translation_status.get("current"):
        current_processing["ollama"] = translation_status["current"].get("source")
    resp = make_response(jsonify({
        "whisper": {
            "status": get_container_status("whisper-asr"),
            "stats": get_container_stats("whisper-asr"),
            "processing": get_cpu_status("whisper-asr", 80),
        },
        "ollama": {
            "status": get_container_status("ollama"),
            "stats": get_container_stats("ollama"),
            "processing": get_cpu_status("ollama", 50),
            "models": get_ollama_models(),
        },
        "bazarr": {
            "status": get_container_status("bazarr"),
            "stats": get_container_stats("bazarr"),
            "activity": get_bazarr_activity(),
        },
        "translation": translation_status,
        "current_processing": current_processing,
        "candidates": candidate_cache,
        "srt_files": get_recent_srt(),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/translate/jobs")
def translate_jobs():
    return jsonify(translation_manager.get_status())


@app.route("/api/translate/trigger", methods=["POST"])
def translate_trigger():
    payload = request.json or {}
    job = payload.get("job")
    path = payload.get("path")
    if job:
        if translation_manager.add_job(job):
            return jsonify({"status": "queued"})
        return jsonify({"status": "already_queued_or_done"})
    if path and os.path.exists(path):
        if translation_manager.add_job(path):
            return jsonify({"status": "queued"})
        return jsonify({"status": "already_queued_or_done"})
    return jsonify({"error": "invalid path"}), 400


@app.route("/api/translate/cancel", methods=["POST"])
def translate_cancel():
    translation_manager.cancel_current()
    return jsonify({"status": "cancelled"})


start_watcher()
start_scanner()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8989, debug=False)
