#!/usr/bin/env bash
# Bazarr post-processing script: auto-translate English subtitles to PT-BR via Ollama.
# Place this path in Bazarr: Settings -> Subtitles -> Post-Processing -> Post-Processing Script
#
# Environment variables injected by Bazarr:
#   SUBTITLE_PATH            - full path to the downloaded subtitle
#   SUBTITLE_LANGUAGE_CODE3  - ISO 639-3 code of the subtitle language (e.g. eng, por)
#
# Optional environment variables:
#   TRANSLATE_MODEL  - Ollama model to use (default: qwen2.5:7b)
#   OLLAMA_URL       - Ollama API endpoint (default: http://ollama:11434/api/generate)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRANSLATOR="${SCRIPT_DIR}/translate-srt-ollama.py"
OLLAMA_URL="${OLLAMA_URL:-http://ollama:11434/api/generate}"
MODEL="${TRANSLATE_MODEL:-qwen2.5:7b}"

# Only translate if the subtitle language is English
if [[ "${SUBTITLE_LANGUAGE_CODE3:-}" != "eng" ]]; then
    echo "Subtitle is not English (${SUBTITLE_LANGUAGE_CODE3:-unknown}), skipping translation."
    exit 0
fi

if [[ ! -f "$SUBTITLE_PATH" ]]; then
    echo "Subtitle file not found: $SUBTITLE_PATH"
    exit 1
fi

# Build the PT-BR output filename (e.g. file.en.srt -> file.pt-BR.srt)
# Bazarr already saves alongside the media file.
BASE="${SUBTITLE_PATH%.*}"   # strip extension (.srt)
EXT="${SUBTITLE_PATH##*.}"   # get extension
# Bazarr saves English subs as file.en.srt, so strip the .en language code too
if [[ "$BASE" == *.en ]]; then
    BASE="${BASE%.en}"
fi
OUTPUT="${BASE}.pt-BR.${EXT}"

# Avoid overwriting existing PT-BR subtitle
if [[ -f "$OUTPUT" ]]; then
    echo "PT-BR subtitle already exists: $OUTPUT"
    exit 0
fi

echo "Translating $SUBTITLE_PATH -> $OUTPUT"
echo "Using model: $MODEL"

export OLLAMA_URL
python3 "$TRANSLATOR" "$SUBTITLE_PATH" "$OUTPUT" "$MODEL" "Brazilian Portuguese"

echo "Translation finished."
