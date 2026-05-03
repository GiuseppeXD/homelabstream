import re

import httpx

from config import OLLAMA_URL, TRANSLATE_MODEL, BATCH_SIZE, NUM_PREDICT
from scanner import is_english_lang


class TranslationBatchError(Exception):
    pass


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
        "Use natural, conversational Brazilian Portuguese for dialogue.",
        "Keep character names, Stand names, honorifics, and unique terms unchanged.",
        "Do not omit or summarize any content. Preserve the full meaning and tone.",
        "Do not leave subtitle lines in English unless they are proper nouns or intentionally unchanged terms.",
        "Return exactly one line per subtitle item.",
        "If a subtitle has multiple lines of text, join them with literal backslash-n (\\n).",
        "Use the format: NUMBER. text",
    ]
    for n, entry in enumerate(batch, 1):
        text = entry["text"].replace("\n", "\\n")
        prompt_lines.append(f"{n}. {text}")
    return "\n".join(prompt_lines)


def parse_batch_response(raw, expected_count):
    result = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\d+[.)]\s*(.*)", line)
        if match:
            text = match.group(1)
            text = text.replace("\\n", "\n")
            result.append(text)
    if len(result) != expected_count:
        return None, f"expected {expected_count} items, got {len(result)}"
    return result, None


def request_batch_translation(client, batch, source_label, batch_label):
    prompt = build_prompt(batch, source_label)
    response = client.post(OLLAMA_URL, json={
        "model": TRANSLATE_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": NUM_PREDICT},
    })
    response.raise_for_status()
    raw = response.json().get("response", "").strip()
    batch_translated, err = parse_batch_response(raw, len(batch))
    if err:
        raise TranslationBatchError(
            f"batch {batch_label} parse error: {err}; raw={raw[:500]}"
        )
    return batch_translated


def translate_batch_with_retry(client, batch, source_label, batch_label, cancel_check=None):
    if cancel_check and cancel_check():
        raise TranslationBatchError(f"batch {batch_label} cancelled")

    try:
        return request_batch_translation(client, batch, source_label, batch_label)
    except Exception as exc:
        if len(batch) == 1:
            raise TranslationBatchError(f"batch {batch_label} failed permanently: {exc}") from exc

        mid = len(batch) // 2
        left = batch[:mid]
        right = batch[mid:]
        print(
            f"Ollama batch {batch_label} failed, retrying split "
            f"{len(batch)} -> {len(left)} + {len(right)}: {exc}"
        )
        left_result = translate_batch_with_retry(client, left, source_label, f"{batch_label}a", cancel_check)
        right_result = translate_batch_with_retry(client, right, source_label, f"{batch_label}b", cancel_check)
        return left_result + right_result


def translate_srt(source_path, output_path, source_language, cancel_check=None):
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

            try:
                batch_translated = translate_batch_with_retry(
                    client,
                    batch,
                    source_label,
                    str(batch_num),
                    cancel_check=cancel_check,
                )
            except Exception as exc:
                print(f"Ollama batch {batch_num} failed permanently: {exc}")
                return False

            for entry, text in zip(batch, batch_translated):
                translated.append({**entry, "text": text})

    with open(output_path, "w", encoding="utf-8") as handle:
        for i, entry in enumerate(translated):
            if i:
                handle.write("\n\n")
            handle.write(f"{entry['seq']}\n{entry['timestamp']}\n{entry['text']}")
        handle.write("\n")
    return True
