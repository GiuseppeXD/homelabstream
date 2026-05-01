import os

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from config import SUBTITLE_EXTENSIONS
from scanner import media_roots, is_subtitle, is_ptbr_lang, lang_from_subtitle_name, subtitle_output_path


class SubtitleWatcher(PatternMatchingEventHandler):
    def __init__(self, add_job_func):
        patterns = [f"*{ext}" for ext in SUBTITLE_EXTENSIONS]
        super().__init__(patterns=patterns, ignore_directories=True)
        self.add_job = add_job_func

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
        self.add_job({"source": path, "source_type": "external", "language": lang, "output": subtitle_output_path(path)})


_observer = None


def start_watcher(add_job_func):
    global _observer
    if _observer is not None:
        return
    _observer = Observer()
    for watch_dir in media_roots():
        if os.path.exists(watch_dir):
            _observer.schedule(SubtitleWatcher(add_job_func), watch_dir, recursive=True)
            print(f"Watching {watch_dir}")
    _observer.start()
