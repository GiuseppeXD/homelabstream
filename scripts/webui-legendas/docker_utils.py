import subprocess


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


def get_bazarr_activity():
    logs = run_cmd("docker logs --since 5m bazarr 2>/dev/null | grep -iE 'whisper|subtitle|download|processing' | tail -5")
    lines = [line.strip() for line in logs.split("\n") if line.strip()]
    return lines[-5:] if lines else ["No recent activity"]
