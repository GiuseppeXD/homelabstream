from flask import Flask, render_template, jsonify, make_response
import subprocess
import json
import os
import time
from datetime import datetime

app = Flask(__name__)

MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "5"))

def run_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        # Docker logs often outputs to stderr, so combine both
        output = result.stdout.strip()
        if not output and result.stderr:
            output = result.stderr.strip()
        return output
    except Exception:
        return ""

def get_container_stats(name):
    """Get CPU and memory usage for a container."""
    try:
        # Use table format and parse second line (first line is header)
        output = run_cmd(f"docker stats --no-stream {name}")
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        if len(lines) >= 2:
            parts = lines[1].split()
            # Format: CONTAINER_ID NAME CPU% MEM_USAGE / LIMIT MEM% NET_I/O BLOCK_I/O PIDS
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
    """Check if container is running."""
    output = run_cmd(f"docker ps --filter 'name={name}'")
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    if len(lines) >= 2:
        parts = lines[1].split()
        # Format: CONTAINER_ID IMAGE COMMAND CREATED STATUS PORTS NAMES
        # Status starts with "Up" or "Exited", usually around index 4-5
        for i, part in enumerate(parts):
            if part.startswith("Up") or part.startswith("Exited"):
                return " ".join(parts[i:i+3]) if i+3 <= len(parts) else part
    return "stopped"

def get_whisper_status():
    """Check if whisper is actively processing by CPU usage."""
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
    """Check if ollama is actively translating by CPU usage."""
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
    """List available ollama models."""
    models = run_cmd("docker exec ollama ollama list 2>/dev/null | tail -n +2 | awk '{print $1}'")
    return [m.strip() for m in models.split("\n") if m.strip()]

def get_recent_srt():
    """Get recently created SRT files."""
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
            
            # Determine type
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
            
            # Human readable size
            if size > 1024*1024:
                size_str = f"{size/(1024*1024):.1f}MB"
            elif size > 1024:
                size_str = f"{size/1024:.0f}KB"
            else:
                size_str = f"{size}B"
            
            # Time ago
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

def get_current_processing():
    """Try to identify what file is currently being processed.
    
    Only reports files that are actively being worked on:
    - Whisper: log entry exists AND .en.srt does NOT exist yet (or was created very recently)
    - Ollama: .en.srt exists AND .pt-BR.srt does NOT exist yet (within last 240 min)
    """
    result = {"whisper": None, "ollama": None}
    
    # Check bazarr logs for whisper processing (read from end, stop at first match)
    try:
        log_dir = os.getenv("BAZARR_LOG_DIR", "/bazarr-logs")
        log_file = os.path.join(log_dir, "bazarr.log")
        if os.path.exists(log_file):
            import re
            # Read file backwards line by line until we find Whisper entries
            whisper_lines = []
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(0, 2)  # Seek to end
                end_pos = f.tell()
                chunk_size = 8192
                buffer = ''
                pos = end_pos
                while pos > 0 and len(whisper_lines) < 10:
                    read_size = min(chunk_size, pos)
                    pos -= read_size
                    f.seek(pos)
                    chunk = f.read(read_size)
                    buffer = chunk + buffer
                    lines = buffer.split('\n')
                    buffer = lines[0] if lines else ''
                    for line in reversed(lines[1:]):
                        if 'WhisperAI Starting' in line or 'whisper query result' in line:
                            whisper_lines.append(line)
                    if pos == 0 and buffer:
                        if 'WhisperAI Starting' in buffer or 'whisper query result' in buffer:
                            whisper_lines.append(buffer)
                        break
            
            if whisper_lines:
                # Process most recent whisper line
                log_text = '\n'.join(whisper_lines)
                # Match: "for /media/..." or "for \"/media/...\" or "for ?(/media/...)"
                matches = re.findall(r'for\s+"?\??(/media/.+?\.(?:mkv|mp4|avi))', log_text)
                if matches:
                    mkv_path = matches[0]
                    base = os.path.splitext(mkv_path)[0]
                    en_srt = base + '.en.srt'
                    # Only show as processing if EN subtitle doesn't exist yet
                    # or was created in the last 5 minutes (race condition)
                    if not os.path.exists(en_srt):
                        result["whisper"] = os.path.basename(mkv_path)
                    elif os.path.exists(en_srt):
                        # Check if .en.srt is very recent (< 5 min) - whisper might still be finishing
                        en_mtime = os.path.getmtime(en_srt)
                        if time.time() - en_mtime < 300:
                            result["whisper"] = os.path.basename(mkv_path)
    except Exception as e:
        print(f"Error reading bazarr logs: {e}")
    
    # Fallback: if whisper CPU is high but we couldn't identify the file from logs,
    # at least report that whisper is actively processing
    if result["whisper"] is None:
        try:
            output = run_cmd("docker stats --no-stream whisper-asr")
            lines = [l.strip() for l in output.splitlines() if l.strip()]
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 3:
                    cpu_str = parts[2].replace('%', '')
                    cpu_val = float(cpu_str)
                    if cpu_val > 80:
                        result["whisper"] = "Processando (arquivo não identificado)"
        except:
            pass
    
    # Check for EN SRT files without PT-BR (waiting for ollama)
    # Only consider files from last 240 min (4h) to avoid showing stale failed jobs
    try:
        recent_files = run_cmd(f"find {MEDIA_DIR} -name '*.en.srt' -mmin -240 2>/dev/null")
        if recent_files:
            lines = [l.strip() for l in recent_files.split('\n') if l.strip()]
            for f in lines:
                pt_br = f.replace('.en.srt', '.pt-BR.srt')
                if os.path.exists(f) and not os.path.exists(pt_br):
                    result["ollama"] = os.path.basename(f).replace('.en.srt', '')
                    break
    except:
        pass
    
    return result

def get_bazarr_activity():
    """Get recent bazarr activity from logs."""
    logs = run_cmd("docker logs --since 5m bazarr 2>/dev/null | grep -iE 'whisper|subtitle|download|processing' | tail -5")
    lines = [l.strip() for l in logs.split("\n") if l.strip()]
    return lines[-5:] if lines else ["No recent activity"]

@app.route("/")
def index():
    return render_template("index.html", refresh_interval=REFRESH_INTERVAL)

@app.route("/api/status")
def api_status():
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
        "current_processing": get_current_processing(),
        "srt_files": get_recent_srt(),
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8989, debug=False)
