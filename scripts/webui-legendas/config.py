import os

MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "5"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "qwen2.5:7b")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
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
