import re

import httpx

from config import OLLAMA_URL, TRANSLATE_MODEL, BATCH_SIZE, NUM_PREDICT
from scanner import is_english_lang


def detect_source_label(source_language):
    if is_english_lang(source_language):
        return "English"
    return f"language code {source_language}"


CLEAN_FANSUB = re.compile(r"\{[^}]*\}")
CLEAN_HTML = re.compile(r"<[^>]*>")
CLEAN_SPACES = re.compile(r" +")


def strip_fansub_notes(text):
    text = CLEAN_FANSUB.sub("", text)
    text = CLEAN_HTML.sub("", text)
    text = CLEAN_SPACES.sub(" ", text)
    return text.strip()


def parse_srt_entries(content):
    entries = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = block.strip().split("\n")
        if len(lines) >= 3 and lines[0].strip().isdigit():
            text = "\n".join(lines[2:])
            text = strip_fansub_notes(text)
            if not text:
                text = " "
            entries.append({
                "seq": lines[0].strip(),
                "timestamp": lines[1].strip(),
                "text": text,
            })
    return entries


def build_prompt(batch, source_label):
    prompt_lines = [
        f"Translate these subtitles from {source_label} to Brazilian Portuguese.",
        "Keep names, honorifics, tone, and line breaks where useful.",
        "Return ONLY numbered translated lines in the same order.",
    ]
    for n, entry in enumerate(batch, 1):
        prompt_lines.append(f"{n}. {entry['text']}")
    return "\n".join(prompt_lines)


def parse_batch_response(raw):
    batch_translated = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\d+[.)]\s*(.*)", line)
        batch_translated.append(match.group(1) if match else line)
    return batch_translated


def translate_srt(source_path, output_path, source_language, cancel_check=None):
    import time as _time

    with open(source_path, "r", encoding="utf-8-sig") as handle:
        content = handle.read().replace("\r\n", "\n").replace("\r", "\n")

    entries = parse_srt_entries(content)
    if not entries:
        print(f"translate_srt: no valid SRT entries in {source_path} (first 200 bytes: {content[:200].strip()})")
        return False

    source_label = detect_source_label(source_language)
    translated = []

    with httpx.Client(timeout=httpx.Timeout(600)) as client:
        for i in range(0, len(entries), BATCH_SIZE):
            if cancel_check and cancel_check():
                return False

            batch = entries[i : i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            prompt = build_prompt(batch, source_label)

            try:
                response = client.post(OLLAMA_URL, json={
                    "model": TRANSLATE_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": NUM_PREDICT},
                })
                response.raise_for_status()
                raw = response.json().get("response", "").strip()
                batch_translated = parse_batch_response(raw)
            except Exception as exc:
                print(f"Ollama batch {batch_num} failed: {exc}")
                batch_translated = [entry["text"] for entry in batch]

            if len(batch_translated) < len(batch):
                batch_translated.extend(entry["text"] for entry in batch[len(batch_translated):])
            elif len(batch_translated) > len(batch):
                batch_translated = batch_translated[:len(batch)]

            for entry, text in zip(batch, batch_translated):
                translated.append({**entry, "text": text})

    with open(output_path, "w", encoding="utf-8") as handle:
        for i, entry in enumerate(translated):
            if i:
                handle.write("\n\n")
            handle.write(f"{entry['seq']}\n{entry['timestamp']}\n{entry['text']}")
        handle.write("\n")
    return True
