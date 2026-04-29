from flask import Flask, render_template, jsonify, make_response, request
import subprocess
import json
import os
import time
import threading
import queue
import requests as req
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

app = Flask(__name__)

MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "5"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "qwen2.5:7b")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "40"))
NUM_PREDICT = int(os.getenv("NUM_PREDICT", "2048"))

# ── Translation Manager ──────────────────────────────────────────────

class TranslationManager:
    def __init__(self):
        self.pending = queue.Queue()
        self.current = None
        self.current_start = None
        self.completed = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cancelled = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
    
    def add_job(self, path):
        """Add an EN SRT file to the translation queue."""
        if not os.path.exists(path):
            return False
        pt_br = path.replace('.en.srt', '.pt-BR.srt')
        if os.path.exists(pt_br):
            return False
        # Check if already in queue
        with self._lock:
            if self.current and self.current.get("path") == path:
                return False
            for item in list(self.pending.queue):
                if item == path:
                    return False
        self.pending.put(path)
        return True
    
    def cancel_current(self):
        """Signal cancellation of the current job."""
        self._cancelled.set()
    
    def _worker(self):
        while not self._stop_event.is_set():
            try:
                path = self.pending.get(timeout=1)
            except queue.Empty:
                continue
            
            self._cancelled.clear()
            with self._lock:
                self.current = {"path": path, "filename": os.path.basename(path)}
                self.current_start = time.time()
            
            try:
                success = self._translate(path)
                if success:
                    self.completed.append({
                        "path": path,
                        "filename": os.path.basename(path),
                        "completed_at": datetime.now().strftime("%H:%M:%S")
                    })
            except Exception as e:
                print(f"Translation failed for {path}: {e}")
            
            with self._lock:
                self.current = None
                self.current_start = None
            self.pending.task_done()
    
    def _translate(self, path):
        """Translate SRT via Ollama API. Inline implementation of translate-srt-ollama.py."""
        import re
        
        output_path = path.replace('.en.srt', '.pt-BR.srt')
        
        # Read EN SRT
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse SRT
        entries = []
        for block in re.split(r'\n\n+', content.strip()):
            lines = block.strip().split('\n')
            if len(lines) >= 3 and lines[0].isdigit():
                seq = lines[0]
                timestamp = lines[1]
                text = '\n'.join(lines[2:])
                entries.append({"seq": seq, "timestamp": timestamp, "text": text})
        
        if not entries:
            return False
        
        # Translate in batches
        translated = []
        for i in range(0, len(entries), BATCH_SIZE):
            if self._cancelled.is_set():
                return False
            
            batch = entries[i:i+BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(entries) + BATCH_SIZE - 1) // BATCH_SIZE
            
            # Build prompt
            prompt_lines = ["Translate the following English subtitles to Brazilian Portuguese. Keep the numbering and respond with ONLY the translated lines, one per item."]
            for e in batch:
                prompt_lines.append(f"{e['seq']}. {e['text']}")
            prompt = "\n".join(prompt_lines)
            
            # Call Ollama
            try:
                response = req.post(OLLAMA_URL, json={
                    "model": TRANSLATE_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": NUM_PREDICT}
                }, timeout=300)
                response.raise_for_status()
                result = response.json()
                raw = result.get("response", "").strip()
                
                # Parse response
                batch_translated = []
                for line in raw.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    # Remove leading number like "1. " or "1) "
                    match = re.match(r'^\d+[.\)]\s*(.*)', line)
                    if match:
                        batch_translated.append(match.group(1))
                    else:
                        batch_translated.append(line)
                
                # Handle count mismatch
                if len(batch_translated) < len(batch):
                    batch_translated.extend([batch[j]["text"] for j in range(len(batch_translated), len(batch))])
                elif len(batch_translated) > len(batch):
                    batch_translated = batch_translated[:len(batch)]
                
                for j, t in enumerate(batch_translated):
                    translated.append({
                        "seq": batch[j]["seq"],
                        "timestamp": batch[j]["timestamp"],
                        "text": t
                    })
                
            except Exception as e:
                print(f"Ollama batch {batch_num} failed: {e}")
                # Fallback: keep original text
                for e in batch:
                    translated.append(e)
        
        # Write PT-BR SRT
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, e in enumerate(translated):
                if i > 0:
                    f.write('\n\n')
                f.write(f"{e['seq']}\n{e['timestamp']}\n{e['text']}")
            f.write('\n')
        
        return True
    
    def get_status(self):
        with self._lock:
            current_info = None
            if self.current and self.current_start:
                elapsed = int(time.time() - self.current_start)
                current_info = {
                    **self.current,
                    "elapsed": elapsed,
                    "status": "running"
                }
            return {
                "current": current_info,
                "pending_count": self.pending.qsize(),
                "pending": list(self.pending.queue),
                "completed": self.completed[-20:]  # last 20
            }

translation_manager = TranslationManager()

# ── SRT Watcher ──────────────────────────────────────────────────────

class SrtWatcher(PatternMatchingEventHandler):
    def __init__(self, manager):
        super().__init__(patterns=["*.en.srt"], ignore_directories=True)
        self.manager = manager
    
    def on_created(self, event):
        if not event.is_directory:
            self.manager.add_job(event.src_path)
    
    def on_modified(self, event):
        if not event.is_directory:
            self.manager.add_job(event.src_path)

observer = None

def start_watcher():
    global observer
    if observer is not None:
        return
    observer = Observer()
    for watch_dir in [os.path.join(MEDIA_DIR, "series"), os.path.join(MEDIA_DIR, "movies")]:
        if os.path.exists(watch_dir):
            handler = SrtWatcher(translation_manager)
            observer.schedule(handler, watch_dir, recursive=True)
            print(f"Watching {watch_dir}")
    observer.start()

# ── Existing Dashboard Functions ─────────────────────────────────────

def run_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        output = result.stdout.strip()
        if not output and result.stderr:
            output = result.stderr.strip()
        return output
    except Exception:
        return ""

def get_container_stats(name):
    try:
        output = run_cmd(f"docker stats --no-stream {name}")
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 7:
                return {
                    "cpu": parts[2],
                    "mem_usage": parts[3] + " " + parts[4] + " " + parts[5],
                    "mem_perc": parts[6]
                }
    except Exception:
        pass
    return {"cpu": "--", "mem_usage": "--", "mem_perc": "--"}

def get_container_status(name):
    output = run_cmd(f"docker ps --filter 'name={name}'")
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    if len(lines) >= 2:
        parts = lines[1].split()
        for i, part in enumerate(parts):
            if part.startswith("Up") or part.startswith("Exited"):
                return " ".join(parts[i:i+3]) if i+3 <= len(parts) else part
    return "stopped"

def get_whisper_status():
    try:
        output = run_cmd("docker stats --no-stream whisper-asr")
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 3:
                cpu_str = parts[2].replace('%', '')
                cpu_val = float(cpu_str)
                return "processing" if cpu_val > 80 else "idle"
    except:
        pass
    return "unknown"

def get_ollama_status():
    try:
        output = run_cmd("docker stats --no-stream ollama")
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 3:
                cpu_str = parts[2].replace('%', '')
                cpu_val = float(cpu_str)
                return "processing" if cpu_val > 50 else "idle"
    except:
        pass
    return "unknown"

def get_ollama_models():
    models = run_cmd("docker exec ollama ollama list 2>/dev/null | tail -n +2 | awk '{print $1}'")
    return [m.strip() for m in models.split("\n") if m.strip()]

def get_recent_srt():
    files = []
    try:
        cmd = f"find {MEDIA_DIR} -name '*.srt' -mmin -2880 -printf '%T@|%s|%p\\n' 2>/dev/null | sort -rn | head -20"
        output = run_cmd(cmd)
        for line in output.split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            mtime = float(parts[0])
            size = int(parts[1])
            path = parts[2]
            filename = os.path.basename(path)
            if ".pt-BR.srt" in filename:
                lang = "pt-BR"
                flag = "🇧🇷"
            elif ".en.srt" in filename:
                lang = "en"
                flag = "🇺🇸"
            else:
                lang = "other"
                flag = "🌐"
            if size > 1024*1024:
                size_str = f"{size/(1024*1024):.1f}MB"
            elif size > 1024:
                size_str = f"{size/1024:.0f}KB"
            else:
                size_str = f"{size}B"
            elapsed = time.time() - mtime
            if elapsed < 60:
                ago = f"{int(elapsed)}s"
            elif elapsed < 3600:
                ago = f"{int(elapsed/60)}m"
            elif elapsed < 86400:
                ago = f"{int(elapsed/3600)}h"
            else:
                ago = f"{int(elapsed/86400)}d"
            files.append({
                "path": path,
                "filename": filename,
                "lang": lang,
                "flag": flag,
                "size": size_str,
                "ago": ago,
                "timestamp": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            })
    except Exception as e:
        print(f"Error getting SRT files: {e}")
    return files

def get_en_srt_without_ptbr():
    """Find EN SRT files that are waiting for translation."""
    files = []
    try:
        cmd = f"find {MEDIA_DIR}/series {MEDIA_DIR}/movies -name '*.en.srt' 2>/dev/null"
        output = run_cmd(cmd)
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            pt_br = line.replace('.en.srt', '.pt-BR.srt')
            if os.path.exists(line) and not os.path.exists(pt_br):
                files.append({
                    "path": line,
                    "filename": os.path.basename(line),
                    "mtime": datetime.fromtimestamp(os.path.getmtime(line)).strftime("%Y-%m-%d %H:%M")
                })
    except Exception:
        pass
    return files

def get_bazarr_activity():
    logs = run_cmd("docker logs --since 5m bazarr 2>/dev/null | grep -iE 'whisper|subtitle|download|processing' | tail -5")
    lines = [l.strip() for l in logs.split("\n") if l.strip()]
    return lines[-5:] if lines else ["No recent activity"]

# ── Flask Routes ─────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", refresh_interval=REFRESH_INTERVAL)

@app.route("/api/status")
def api_status():
    translation_status = translation_manager.get_status()
    current_processing = {}
    if translation_status.get("current"):
        current_processing["ollama"] = translation_status["current"]["path"]
    resp = make_response(jsonify({
        "whisper": {
            "status": get_container_status("whisper-asr"),
            "stats": get_container_stats("whisper-asr"),
            "processing": get_whisper_status()
        },
        "ollama": {
            "status": get_container_status("ollama"),
            "stats": get_container_stats("ollama"),
            "processing": get_ollama_status(),
            "models": get_ollama_models()
        },
        "bazarr": {
            "status": get_container_status("bazarr"),
            "stats": get_container_stats("bazarr"),
            "activity": get_bazarr_activity()
        },
        "translation": translation_status,
        "current_processing": current_processing,
        "en_files": get_en_srt_without_ptbr(),
        "srt_files": get_recent_srt(),
        "timestamp": datetime.now().strftime("%H:%M:%S")
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
    path = request.json.get("path") if request.json else None
    if path and os.path.exists(path):
        if translation_manager.add_job(path):
            return jsonify({"status": "queued"})
        return jsonify({"status": "already_queued_or_done"})
    return jsonify({"error": "invalid path"}), 400

@app.route("/api/translate/cancel", methods=["POST"])
def translate_cancel():
    translation_manager.cancel_current()
    return jsonify({"status": "cancelled"})

# ── Startup ──────────────────────────────────────────────────────────

@app.before_request
def _start_watcher_once():
    if not getattr(_start_watcher_once, "done", False):
        start_watcher()
        _start_watcher_once.done = True

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8989, debug=False)
