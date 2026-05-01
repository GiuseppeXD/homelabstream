import json
import hashlib
import re
from pathlib import Path

from docker_utils import run_exec

CLEAN_FANSUB = re.compile(r"\{[^}]*\}")
CLEAN_HTML = re.compile(r"<[^>]*>")
CLEAN_SPACES = re.compile(r" +")


def source_cache_path(job):
    cache_dir = Path("/tmp/legendas-webui")
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = Path(job["output"])
    lang = job.get("language", "unknown")
    source_type = job.get("source_type", "external")
    digest = hashlib.sha1(f"{job.get('source')}|{job.get('stream_index')}|{output}".encode()).hexdigest()[:12]
    return str(cache_dir / f"{output.stem}.{source_type}.{lang}.{digest}.srt")


def ffprobe_subtitles(video_path):
    try:
        result = run_exec([
            "ffprobe",
            "-v", "error",
            "-select_streams", "s",
            "-show_entries", "stream=index,codec_name:stream_tags=language,title",
            "-of", "json",
            video_path,
        ], timeout=30)
        if result.returncode != 0:
            return []
        return json.loads(result.stdout or "{}").get("streams", [])
    except Exception as exc:
        print(f"ffprobe failed for {video_path}: {exc}")
        return []


def extract_embedded(source, stream_index, target, timeout=300):
    result = run_exec([
        "ffmpeg", "-y", "-i", source,
        "-map", f"0:{stream_index}", target,
    ], timeout=timeout)
    return result.returncode == 0, result.stderr[-1000:] if result.stderr else ""


def convert_to_srt(source, target, timeout=120):
    result = run_exec(["ffmpeg", "-y", "-i", source, target], timeout=timeout)
    return result.returncode == 0, result.stderr[-1000:] if result.stderr else ""


def clean_srt(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            content = handle.read()
        cleaned = CLEAN_FANSUB.sub("", content)
        cleaned = CLEAN_HTML.sub("", cleaned)
        cleaned = CLEAN_SPACES.sub(" ", cleaned)
        if cleaned != content:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(cleaned)
    except Exception as exc:
        print(f"Failed to clean fansub notes from {path}: {exc}")


def prepare_subtitle_source(job):
    source = job["source"]
    source_type = job.get("source_type", "external")

    if source_type == "embedded":
        target = source_cache_path(job)
        ok, err = extract_embedded(source, job["stream_index"], target)
        if not ok:
            print(f"ffmpeg extract failed for {source}: {err}")
            return None
        clean_srt(target)
        return target

    suffix = Path(source).suffix.lower()
    if suffix == ".srt":
        clean_srt(source)
        return source

    target = source_cache_path(job)
    ok, err = convert_to_srt(source, target)
    if not ok:
        print(f"ffmpeg convert failed for {source}: {err}")
        return None
    clean_srt(target)
    return target
