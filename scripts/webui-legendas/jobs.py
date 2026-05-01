import os
import queue
import threading
import time
from datetime import datetime

from db import (
    init_db, insert_job, update_job_status, mark_translated,
    load_pending_jobs, get_completed_jobs, job_source_exists,
    cleanup_old_jobs,
)
from extractor import prepare_subtitle_source
from translate import translate_srt
from scanner import is_ptbr_lang, lang_from_subtitle_name

init_db()


class JobManager:
    def __init__(self):
        self._pending = queue.Queue()
        self._current = None
        self._current_db_id = None
        self._current_start = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cancelled = threading.Event()
        self._on_change = None

        self._reload_pending()

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def set_on_change(self, callback):
        self._on_change = callback

    def _notify(self):
        if self._on_change:
            try:
                self._on_change()
            except Exception as exc:
                print(f"on_change callback failed: {exc}")

    def _reload_pending(self):
        pending = load_pending_jobs()
        for job in pending:
            self._pending.put(job)

    def add_job(self, data):
        if isinstance(data, str):
            job = {"source": data, "source_type": "external"}
        else:
            job = dict(data)

        job.setdefault("source_type", "external")
        job.setdefault("language", lang_from_subtitle_name(job["source"]))

        if not os.path.exists(job["source"]):
            return False
        if os.path.exists(job.get("output", "")):
            return False
        if is_ptbr_lang(job.get("language")):
            return False
        if job_source_exists(job["source"], job.get("output", "")):
            return False

        try:
            job_id = insert_job(job)
            job["id"] = job_id
            self._pending.put(job)
            self._notify()
            return True
        except Exception as exc:
            print(f"Failed to insert job: {exc}")
            return False

    def cancel_current(self):
        self._cancelled.set()

    def _worker(self):
        while not self._stop_event.is_set():
            try:
                job = self._pending.get(timeout=1)
            except queue.Empty:
                continue

            self._cancelled.clear()
            job_id = job.get("id")
            with self._lock:
                self._current = dict(job)
                self._current_db_id = job_id
                self._current_start = time.time()

            if job_id:
                update_job_status(job_id, "running")
            self._notify()

            try:
                success = self._process_job(job)
                if success and job_id:
                    update_job_status(job_id, "completed")
                    mark_translated(
                        job.get("output", ""),
                        job["source"],
                        job.get("source_type", "external"),
                        job.get("language", "unknown"),
                    )
                elif job_id:
                    update_job_status(job_id, "failed", "Translation failed")
            except Exception as exc:
                print(f"Translation failed for {job.get('source')}: {exc}")
                if job_id:
                    update_job_status(job_id, "failed", str(exc))
            finally:
                with self._lock:
                    self._current = None
                    self._current_db_id = None
                    self._current_start = None
                self._pending.task_done()
                self._notify()
                cleanup_old_jobs()

    def _process_job(self, job):
        source_srt = prepare_subtitle_source(job)
        if not source_srt:
            return False
        return translate_srt(
            source_srt,
            job["output"],
            job.get("language", "unknown"),
            cancel_check=self._cancelled.is_set,
        )

    def get_status(self):
        with self._lock:
            current_info = None
            if self._current and self._current_start:
                current_info = {
                    **self._current,
                    "elapsed": int(time.time() - self._current_start),
                    "status": "running",
                }

            pending_list = list(self._pending.queue)
            completed = get_completed_jobs(20)

            return {
                "current": current_info,
                "pending_count": len(pending_list),
                "pending": pending_list,
                "completed": completed,
            }


job_manager = JobManager()
