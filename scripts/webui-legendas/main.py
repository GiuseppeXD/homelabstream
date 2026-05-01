import asyncio
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from config import REFRESH_INTERVAL
from db import init_db
from scanner import (
    candidate_cache, get_recent_srt, refresh_candidates, scanner_loop,
)
from watcher import start_watcher
from jobs import job_manager
from docker_utils import (
    get_container_stats, get_container_status, get_cpu_status,
    get_ollama_models, get_bazarr_activity,
)

templates = Jinja2Templates(directory="templates")

connected_clients: set[WebSocket] = set()
_loop = None

async def broadcast(data):
    dead = set()
    for ws in connected_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    connected_clients.difference_update(dead)


def notify_all():
    if _loop:
        asyncio.run_coroutine_threadsafe(_broadcast_status(), _loop)


async def _broadcast_status():
    await broadcast(build_status())


def build_status():
    translation_status = job_manager.get_status()
    current_processing = {}
    if translation_status.get("current"):
        current_processing["ollama"] = translation_status["current"].get("source")

    return {
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
    }


def start_background():
    job_manager.set_on_change(notify_all)
    start_watcher(job_manager.add_job)

    def scan_loop():
        while True:
            refresh_candidates()
            queued = 0
            for candidate in candidate_cache["items"]:
                if queued >= int(os.getenv("SUBTITLE_AUTO_QUEUE_LIMIT", "0")):
                    break
                if job_manager.add_job(candidate):
                    queued += 1
            notify_all()
            time.sleep(int(os.getenv("SUBTITLE_SCAN_INTERVAL", "300")))

    threading.Thread(target=scan_loop, daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_running_loop()
    init_db()
    start_background()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"refresh_interval": REFRESH_INTERVAL})


@app.get("/api/status")
async def api_status():
    resp = JSONResponse(build_status())
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.get("/api/translate/jobs")
async def translate_jobs():
    return JSONResponse(job_manager.get_status())


@app.post("/api/translate/trigger")
async def translate_trigger(request: Request):
    payload = await request.json() or {}
    job = payload.get("job")
    path = payload.get("path")
    if job:
        if job_manager.add_job(job):
            return JSONResponse({"status": "queued"})
        return JSONResponse({"status": "already_queued_or_done"})
    if path and os.path.exists(path):
        if job_manager.add_job(path):
            return JSONResponse({"status": "queued"})
        return JSONResponse({"status": "already_queued_or_done"})
    return JSONResponse({"error": "invalid path"}, 400)


@app.post("/api/translate/cancel")
async def translate_cancel():
    job_manager.cancel_current()
    return JSONResponse({"status": "cancelled"})


@app.get("/api/candidates")
async def api_candidates():
    return JSONResponse(candidate_cache)


@app.get("/api/srt/recent")
async def api_srt_recent():
    return JSONResponse(get_recent_srt())


@app.get("/api/jobs")
async def api_list_jobs():
    from db import list_jobs
    return JSONResponse(list_jobs())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        await websocket.send_json(build_status())
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"ping": datetime.now().isoformat()})
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        connected_clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8989, log_level="info")
