import json
import os
import threading
import time
from pathlib import Path

from docker_utils import run_cmd, run_exec
from config import MEDIA_DIR, OLLAMA_URL, TRANSLATE_MODEL, NUM_PREDICT, BATCH_SIZE

WHISPER_CONTAINER = os.getenv("WHISPER_CONTAINER", "whisper-asr")
WHISPER_URL = os.getenv("WHISPER_URL", "http://whisper-asr:9000")
WHISPER_START_TIMEOUT = int(os.getenv("WHISPER_START_TIMEOUT", "180"))
WHISPER_TRANSCRIBE_TIMEOUT = int(os.getenv("WHISPER_TRANSCRIBE_TIMEOUT", "7200"))

_state = {"current": None, "history": []}


def get_state():
    return {"current": _state["current"], "history": _state["history"][-10:]}


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


def segments_to_srt(segments):
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _fmt_ts(seg.get("start", 0))
        end = _fmt_ts(seg.get("end", 0))
        text = seg.get("text", "").strip()
        if not text:
            text = " "
        lines.append(f"{i}\n{start} --> {end}\n{text}")
    return "\n\n".join(lines)


def _fmt_ts(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def translate_srt_via_ollama(srt_path, source_lang, target_lang="English"):
    import httpx
    import re

    with open(srt_path, "r", encoding="utf-8-sig") as f:
        content = f.read().replace("\r\n", "\n").replace("\r", "\n")

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
    label = source_lang if source_lang != "en" else "English"
    with httpx.Client(timeout=httpx.Timeout(600)) as client:
        for i in range(0, len(entries), BATCH_SIZE):
            batch = entries[i : i + BATCH_SIZE]
            prompt_lines = [
                f"Translate these subtitles from {label} to {target_lang}.",
                "Keep names, honorifics, tone, and line breaks where useful.",
                "Return ONLY numbered translated lines in the same order.",
            ]
            for n, entry in enumerate(batch, 1):
                prompt_lines.append(f"{n}. {entry['text']}")
            prompt = "\n".join(prompt_lines)
            try:
                resp = client.post(OLLAMA_URL, json={
                    "model": TRANSLATE_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": NUM_PREDICT},
                }, timeout=600)
                resp.raise_for_status()
                raw = resp.json().get("response", "").strip()
                batch_translated = []
                for line in raw.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    m = re.match(r"^\d+[.)]\s*(.*)", line)
                    batch_translated.append(m.group(1) if m else line)
                if len(batch_translated) < len(batch):
                    batch_translated.extend(e["text"] for e in batch[len(batch_translated):])
                elif len(batch_translated) > len(batch):
                    batch_translated = batch_translated[:len(batch)]
            except Exception as exc:
                print(f"Ollama batch {i//BATCH_SIZE+1} failed: {exc}")
                batch_translated = [e["text"] for e in batch]
            for entry, text in zip(batch, batch_translated):
                translated.append({**entry, "text": text})

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, entry in enumerate(translated):
            if i:
                f.write("\n\n")
            f.write(f"{entry['seq']}\n{entry['timestamp']}\n{entry['text']}")
        f.write("\n")
    return True


def transcribe(video_path):
    url = f"{WHISPER_URL}/asr"
    try:
        result = run_exec([
            "curl", "-s", "-X", "POST",
            "-F", f"audio_file=@{video_path}",
            "-F", "response_format=json",
            url,
        ], timeout=WHISPER_TRANSCRIBE_TIMEOUT)
        if result.returncode != 0:
            return None, None, f"curl failed: {result.stderr.strip()}"
        raw = result.stdout.strip()
        if not raw:
            return None, None, "Resposta vazia da API do Whisper"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None, None, f"Resposta nao-JSON do Whisper: {raw[:200]}"
        if "error" in payload:
            return None, None, str(payload.get("error", raw[:200]))
        lang = payload.get("language", "unknown")
        segments = payload.get("segments", [])
        if not segments:
            return None, None, "Nenhum segmento na resposta do Whisper"
        srt_content = segments_to_srt(segments)
        return srt_content, lang, None
    except Exception as exc:
        return None, None, str(exc)


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
        srt_content, lang, err = transcribe(job["video_path"])
        if err:
            job["status"] = "error"
            job["error"] = err
            return

        job["lang_detected"] = lang

        job["status"] = "saving"
        tmp = job["target"] + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write(srt_content)
        except OSError as exc:
            job["status"] = "error"
            job["error"] = f"Falha ao salvar SRT temporario: {exc}"
            return

        if lang and lang != "en":
            job["status"] = "translating"
            job["error"] = None
            ok = translate_srt_via_ollama(tmp, lang, "English")
            if not ok:
                job["status"] = "error"
                job["error"] = f"Falha ao traduzir de {lang} para ingles via Ollama"
                return

        try:
            os.replace(tmp, job["target"])
        except OSError as exc:
            job["status"] = "error"
            job["error"] = f"Falha ao salvar SRT final: {exc}"
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
