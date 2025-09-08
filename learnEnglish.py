#!/usr/bin/env python3
"""
learnEnglish_fixed.py
- Reads a CSV (one word per row or first column)
- Calls Gemini via the google-genai SDK to get:
    meaning, translation, meaning_translation,
    example_phrase, phrase_translation
- Adds notes to Anki via AnkiConnect.

Usage:
  pip install -U google-genai requests
  export GEMINI_API_KEY="your_key_here"    # recommended
  python learnEnglish_fixed.py words.csv --deck "EnglishAI" --model "EnglishAI"
  or:
  python learnEnglish_fixed.py words.csv --api-key "YOUR_KEY" --dry-run
"""
import argparse
import csv
import json
import os
import re
import time
import logging
from typing import Optional


# try importing google-genai
try:
    from google import genai
    from google.genai import types
except Exception as exc:
    raise ImportError(
        "Missing google-genai package. Install with: pip install google-genai\n"
        f"Original import error: {exc}"
    )

import requests

ANKI_CONNECT_URL = "http://localhost:8765"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def create_genai_client(api_key: Optional[str] = None, http_api_version: Optional[str] = None):
    """Create and return a genai.Client.
       If api_key is None, the client will pick it up from GEMINI_API_KEY / GOOGLE_API_KEY env var."""
    client_kwargs = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if http_api_version:
        # example: types.HttpOptions(api_version="v1")
        client_kwargs["http_options"] = types.HttpOptions(api_version=http_api_version)
    client = genai.Client(**client_kwargs)
    return client


def find_json_in_text(text: str) -> dict:
    """Try to extract a JSON object from a block of text robustly."""
    text = text.strip()
    # Try direct load first
    try:
        return json.loads(text)
    except Exception:
        pass

    # Find the first balanced {...} JSON object using a small scanner
    start = None
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if start is None:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
            if depth == 0 and start is not None:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    # continue scanning for another balanced object
                    start = None
                    depth = 0
                    continue

    # fallback: try to find smaller {...} via regex (non-nested)
    matches = re.findall(r"\{[^{}]+\}", text, flags=re.DOTALL)
    for m in matches:
        try:
            return json.loads(m)
        except Exception:
            continue

    raise ValueError("Could not find a valid JSON object in model response.\nFull response:\n" + text)


def query_gemini_for_word(client, word: str, model: str = DEFAULT_GEMINI_MODEL, retries: int = 2, backoff: float = 1.0):
    """Query Gemini to return the required fields for a single word.
       Returns a dict with keys: meaning, translation, meaning_translation, example_phrase, phrase_translation
    """
    prompt = (
        f"You are a concise, accurate dictionary assistant.\n"
        f"For the English word: \"{word}\"\n\n"
        "Return ONLY a single JSON object and nothing else with these exact keys:\n"
        "  meaning: A concise English definition (one or two short sentences).\n"
        "  translation: The Portuguese translation of the word (single word or short phrase).\n"
        "  meaning_translation: The Portuguese translation of the meaning.\n"
        "  example_phrase: One short natural English sentence that uses the word exactly as given.\n"
        "  phrase_translation: The Portuguese translation of the example phrase.\n\n"
        "Make JSON well-formed and escape quotes as needed. Do NOT wrap the JSON in markdown, commentary, or text."
    )

    attempt = 0
    last_exc = None
    while attempt <= retries:
        attempt += 1
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            # SDK exposes textual output on .text
            raw = response.text
            # Extract JSON robustly
            parsed = find_json_in_text(raw)
            # Normalize keys (strip strings)
            result = {}
            for k in ["meaning", "translation", "meaning_translation", "example_phrase", "phrase_translation"]:
                v = parsed.get(k, "")
                if isinstance(v, str):
                    result[k] = v.strip()
                else:
                    result[k] = json.dumps(v, ensure_ascii=False)
            return result
        except Exception as e:
            last_exc = e
            wait = backoff * attempt
            logging.warning("Gemini request failed (attempt %d/%d): %s — retrying in %.1fs", attempt, retries + 1, e, wait)
            time.sleep(wait)

    # after retries
    raise RuntimeError(f"Gemini requests failed after {retries+1} attempts. Last error: {last_exc}")


def add_anki_note(fields: dict, deck: str, model: str):
    """Add a single note via AnkiConnect. Returns result from Anki_connect."""
    note = {
        "deckName": deck,
        "modelName": model,
        "fields": fields,
        "tags": ["generated_by_gemini"]
    }
    payload = {"action": "addNote", "version": 6, "params": {"note": note}}
    resp = requests.post(ANKI_CONNECT_URL, json=payload, timeout=10)
    resp.raise_for_status()
    ans = resp.json()
    if ans.get("error") is not None:
        raise RuntimeError(f"AnkiConnect error: {ans['error']}")
    return ans.get("result")


def process_csv_file(csv_path: str, client, deck: str, model_name: str, gemini_model: str, dry_run: bool):
    with open(csv_path, newline='', encoding='utf-8') as fh:
        reader = csv.reader(fh)
        row_number = 0
        for row in reader:
            row_number += 1
            if not row:
                continue
            word = row[0].strip()
            if not word:
                continue

            # Skip if note already exists
            if note_exists(word, deck, model_name):
                logging.info("Skipping '%s' — already exists in deck '%s'.", word, deck)
                continue

            logging.info("Processing row %d: %s", row_number, word)
            try:
                gemini = query_gemini_for_word(client, word, model=gemini_model)
                fields = {
                    "Word": word,
                    "Meaning": gemini.get("meaning", ""),
                    "translation": gemini.get("translation", ""),
                    "Meaning Translation": gemini.get("meaning_translation", ""),
                    "example phrase": gemini.get("example_phrase", ""),
                    "phrase translation": gemini.get("phrase_translation", "")
                }

                logging.info("Generated fields for '%s': %s", word, {k: (v[:80] + "..." if len(v) > 80 else v) for k, v in fields.items()})

                if dry_run:
                    logging.info("Dry run: not adding to Anki.")
                else:
                    result = add_anki_note(fields, deck, model_name)
                    logging.info("Added note to Anki (id=%s)", result)
            except Exception as e:
                logging.error("Failed for word '%s' (row %d): %s", word, row_number, e)
            time.sleep(1.0)  # polite pause



def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv", help="CSV file (first column used as word)")
    p.add_argument("--api-key", default=None, help="Gemini API key (optional, use GEMINI_API_KEY env var instead)")
    p.add_argument("--deck", default="EnglishAI", help="Anki deck name")
    p.add_argument("--model", default="EnglishAI", help="Anki note model name")
    p.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL, help="Gemini model to use")
    p.add_argument("--dry-run", action="store_true", help="Don't add to Anki; just print")
    args = p.parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logging.warning("No API key provided via --api-key or GEMINI_API_KEY/GOOGLE_API_KEY environment variables. The client may still work if configured otherwise.")

    client = create_genai_client(api_key=api_key)

    process_csv_file(args.csv, client, args.deck, args.model, args.gemini_model, args.dry_run)

def note_exists(word: str, deck: str, model: str) -> bool:
    """
    Check if a note with the given word already exists in the specified deck and model.
    This assumes the field 'Word' in the note model stores the main word.
    """
    # Adjust field name if your note type uses different capitalization
    query = f'deck:"{deck}" note:"{model}" Word:"{word}"'
    payload = {
        "action": "findNotes",
        "version": 6,
        "params": {"query": query}
    }
    try:
        resp = requests.post(ANKI_CONNECT_URL, json=payload, timeout=10)
        resp.raise_for_status()
        note_ids = resp.json().get("result", [])
        return len(note_ids) > 0
    except Exception as e:
        logging.error("Error checking if note exists for '%s': %s", word, e)
        return False


if __name__ == "__main__":
    main()
