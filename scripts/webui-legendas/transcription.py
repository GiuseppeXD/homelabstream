import os
import threading
import time
from pathlib import Path

from docker_utils import run_cmd, run_exec
from config import MEDIA_DIR

WHISPER_CONTAINER = os.getenv("WHISPER_CONTAINER", "whisper-asr")
WHISPER_URL = os.getenv("WHISPER_URL", "http://whisper-asr:9000")
WHISPER_START_TIMEOUT = int(os.getenv("WHISPER_START_TIMEOUT", "180"))
WHISPER_TRANSCRIBE_TIMEOUT = int(os.getenv("WHISPER_TRANSCRIBE_TIMEOUT", "7200"))


_state = {
    "current": None,
    "history": [],
}


def get_state():
    return {
        "current": _state["current"],
        "history": _state["history"][-10:],
    }


def container_running(name):
    out = run_cmd("docker ps --filter name=%s --format '{{.Status}}'" % name)
    return "Up" in out


def container_exists(name):
    out = run_cmd("docker ps -a --filter name=%s --format '{{.Names}}'" % name)
    return name in out


def start_container(name, timeout=WHISPER_START_TIMEOUT):
    if container_running(name):
        return True
    run_cmd(f"docker start {name}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if container_running(name):
            return True
        time.sleep(2)
    return False


def stop_container(name):
    if not container_running(name):
        return True
    run_cmd(f"docker stop {name}")
    return not container_running(name)


def whisper_healthy(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = run_exec(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", WHISPER_URL], timeout=10)
            code = result.stdout.strip()
            if code and code[0] in ("2", "3"):
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def transcribe(video_path):
    url = f"{WHISPER_URL}/asr"
    try:
        result = run_exec([
            "curl", "-s", "-X", "POST",
            "-F", f"audio_file=@{video_path}",
            "-F", "task=translate",
            "-F", "response_format=srt",
            url,
        ], timeout=WHISPER_TRANSCRIBE_TIMEOUT)
        if result.returncode != 0:
            return None, f"curl failed: {result.stderr.strip()}"
        raw = result.stdout.strip()
        if not raw or "error" in raw.lower():
            return None, raw[:500] if raw else "Resposta vazia"
        return raw, None
    except Exception as exc:
        return None, str(exc)


def trigger(video_path):
    if _state["current"]:
        return False, "Ja existe uma transcricao em andamento"
    abs_path = str(Path(video_path).resolve())
    media_root = Path(MEDIA_DIR).resolve()
    try:
        Path(abs_path).relative_to(media_root)
    except ValueError:
        return False, "Arquivo fora do diretorio de midia"

    target = str(Path(abs_path).with_suffix("")) + ".en.srt"
    if os.path.exists(target):
        return False, f"Arquivo ja existe: {target}"

    job = {
        "video_path": abs_path,
        "target": target,
        "status": "starting",
        "error": None,
        "started_by_us": None,
    }
    _state["current"] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return True, "Transcricao iniciada"


def cancel():
    job = _state["current"]
    if not job:
        return False
    if job.get("started_by_us"):
        stop_container(WHISPER_CONTAINER)
    _state["current"] = None
    return True


def _run(job):
    was_running = container_running(WHISPER_CONTAINER)
    try:
        job["status"] = "starting"
        if not container_exists(WHISPER_CONTAINER):
            job["status"] = "error"
            job["error"] = "Container whisper-asr nao existe. Execute 'docker compose up -d whisper-asr' uma vez no host."
            return

        if not was_running:
            job["started_by_us"] = True
            if not start_container(WHISPER_CONTAINER):
                job["status"] = "error"
                job["error"] = "Falha ao iniciar o container whisper-asr"
                return

        job["status"] = "waiting_api"
        if not whisper_healthy():
            job["status"] = "error"
            job["error"] = "API do Whisper nao respondeu apos iniciar"
            return

        job["status"] = "transcribing"
        result, err = transcribe(job["video_path"])
        if err:
            job["status"] = "error"
            job["error"] = err
            return

        job["status"] = "saving"
        tmp = job["target"] + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write(result)
            os.replace(tmp, job["target"])
        except OSError as exc:
            job["status"] = "error"
            job["error"] = f"Falha ao salvar SRT: {exc}"
            return

        job["status"] = "completed"
    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
    finally:
        _finish(job, was_running)


def _finish(job, was_running=False):
    if job.get("started_by_us") and not was_running:
        stop_container(WHISPER_CONTAINER)
    _state["history"].append(dict(job))
    _state["current"] = None
