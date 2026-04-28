#!/usr/bin/env python3
"""
Translate an SRT subtitle file using a local Ollama LLM.

Usage:
    python3 translate-srt-ollama.py input.srt output.srt [model] [target_lang]

Environment:
    OLLAMA_URL   - Ollama API endpoint (default: http://ollama:11434/api/generate)
    MAX_RETRIES  - Number of retries per batch (default: 2)
    BATCH_SIZE   - Subtitles per batch (default: 40)
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
DEFAULT_MODEL = os.getenv("TRANSLATE_MODEL", "qwen2.5:7b")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "40"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
TIMEOUT = int(os.getenv("TIMEOUT", "600"))


def parse_srt(path: str):
    """Parse SRT into a list of entry dicts. Handles UTF-8 BOM."""
    with open(path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", content.strip())
    entries = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) >= 3 and lines[0].strip().isdigit():
            entries.append(
                {
                    "index": lines[0].strip(),
                    "timecode": lines[1].strip(),
                    "text": "\n".join(lines[2:]),
                }
            )
    return entries


def build_prompt(texts: list[str], target_lang: str) -> str:
    """Build a numbered translation prompt."""
    lines = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    return (
        f"Translate each numbered line below to {target_lang}.\n\n"
        "RULES:\n"
        "- Preserve anime speech style, honorifics, and tone.\n"
        "- Keep line breaks inside segments using the pipe character | .\n"
        "- Return ONLY the numbered translations in the SAME order.\n"
        "- Use the exact format: N. translated text\n\n"
        f"{lines}\n\n"
        "Translations:"
    )


def call_ollama(prompt: str, model: str, attempt: int = 1) -> dict:
    """Call Ollama API with retry logic."""
    data = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 8192,
                "num_predict": 2048,
            },
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"Model '{model}' not found. Run: ollama pull {model}")
        raise
    except Exception as e:
        if attempt < MAX_RETRIES:
            wait = 2 ** attempt
            print(f"  Retry {attempt}/{MAX_RETRIES} after {wait}s... ({e})")
            time.sleep(wait)
            return call_ollama(prompt, model, attempt + 1)
        raise


def parse_numbered_response(raw: str, expected_count: int) -> list[str]:
    """Parse LLM response expecting 'N. text' format."""
    raw = raw.strip()

    # Remove markdown code blocks
    raw = re.sub(r"^```\w*\n?|\n?```$", "", raw).strip()

    # Try to extract numbered lines: "1. text" or "1) text" or "1)text"
    pattern = re.compile(r"^\s*(\d+)[\.\)]\s*(.+)$", re.MULTILINE)
    matches = pattern.findall(raw)

    if matches:
        # Sort by number and extract text
        by_num = {}
        for num_str, text in matches:
            n = int(num_str)
            if n not in by_num:
                by_num[n] = text.strip()
        # Build ordered list
        result = []
        for i in range(1, expected_count + 1):
            if i in by_num:
                result.append(by_num[i])
            else:
                break
        return result

    # Fallback: split by lines and try to find numbered items
    lines = raw.splitlines()
    result = []
    current = ""
    for line in lines:
        m = re.match(r"^\s*(\d+)[\.\)]\s*(.*)$", line)
        if m:
            if current:
                result.append(current.strip())
            current = m.group(2)
        else:
            current += "\n" + line
    if current:
        result.append(current.strip())

    return result


def translate_batch(texts: list[str], target_lang: str, model: str) -> list[str]:
    """Send a batch of subtitle texts to Ollama and return translated texts."""
    expected_count = len(texts)
    prompt = build_prompt(texts, target_lang)

    result = call_ollama(prompt, model)
    raw = result.get("response", "").strip()

    translated = parse_numbered_response(raw, expected_count)

    # Tolerance: accept if close and pad with originals
    tolerance = 2
    diff = len(translated) - expected_count

    if abs(diff) <= tolerance or len(translated) >= expected_count - 1:
        if len(translated) < expected_count:
            print(
                f"  Warning: got {len(translated)}/{expected_count}. Padding missing with original text.",
                file=sys.stderr,
            )
            translated.extend(texts[len(translated):expected_count])
        elif len(translated) > expected_count:
            print(
                f"  Warning: got {len(translated)}/{expected_count}. Truncating extra.",
                file=sys.stderr,
            )
            translated = translated[:expected_count]
        return translated

    # If way off, raise to trigger retry/fallback
    raise RuntimeError(
        f"Segment count mismatch: expected {expected_count}, got {len(translated)}"
    )


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} input.srt output.srt [model] [target_lang]")
        sys.exit(1)

    infile = sys.argv[1]
    outfile = sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_MODEL
    target_lang = sys.argv[4] if len(sys.argv) > 4 else "Brazilian Portuguese"

    entries = parse_srt(infile)
    if not entries:
        print("No valid SRT entries found.")
        sys.exit(1)

    print(f"Loaded {len(entries)} subtitle entries.")
    print(f"Model: {model}, Batch size: {BATCH_SIZE}, Max retries: {MAX_RETRIES}")

    total_batches = (len(entries) - 1) // BATCH_SIZE + 1
    failed_batches = 0

    for i in range(0, len(entries), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch = entries[i : i + BATCH_SIZE]
        texts = [e["text"] for e in batch]
        print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} segments)...")

        try:
            translated = translate_batch(texts, target_lang, model)
        except Exception as exc:
            print(f"  ERROR: {exc}. Keeping original text for this batch.")
            failed_batches += 1
            translated = texts  # keep originals

        for j, entry in enumerate(batch):
            if j < len(translated):
                entry["text"] = translated[j]
            else:
                print(f"  Warning: missing translation for block {entry['index']}", file=sys.stderr)

    with open(outfile, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(f"{entry['index']}\n{entry['timecode']}\n{entry['text']}\n\n")

    print(f"\nDone. Saved to {outfile}")
    if failed_batches:
        print(f"Warning: {failed_batches} batch(es) failed and kept original text.")


if __name__ == "__main__":
    main()
