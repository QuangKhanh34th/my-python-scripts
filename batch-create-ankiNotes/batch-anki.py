import argparse
import datetime
import json
import logging
import os
from pathlib import Path
import sys
import threading
import requests
from google import genai

# --- Configuration & Endpoints ---
YOMITAN_API_URL = "http://127.0.0.1:19633/ankiFields" # Adjust port if your Yomitan local API differs
ANKI_CONNECT_URL = "http://127.0.0.1:8765"
MODEL_NAME = "JPD316"
AI_MODEL_NAME = "gemini-2.5-flash"
AI_SLOW_WARNING_SECONDS = 20
AI_REQUEST_TIMEOUT_SECONDS = 120


def call_anki_connect(action, logger, params=None):
    payload = {
        "action": action,
        "version": 6,
    }
    if params is not None:
        payload["params"] = params

    try:
        response = requests.post(ANKI_CONNECT_URL, json=payload, timeout=AI_REQUEST_TIMEOUT_SECONDS).json()
    except requests.RequestException as e:
        logger.error("AnkiConnect request '%s' failed: %s", action, e)
        return None

    if response.get("error"):
        logger.error("AnkiConnect action '%s' returned error: %s", action, response["error"])
        return None

    return response.get("result")


def get_anki_deck_names(logger):
    result = call_anki_connect("deckNames", logger)
    if not isinstance(result, list):
        return []
    return sorted(result)


def prompt_deck_name(logger):
    deck_names = get_anki_deck_names(logger)
    if not deck_names:
        logger.warning("Could not fetch deck list from AnkiConnect. Please type the deck name manually.")
        return prompt_non_empty("Deck name (example: Japanese::Vocab): ", logger)

    logger.info("Available Anki decks:")
    for i, name in enumerate(deck_names, start=1):
        logger.info("  %d) %s", i, name)

    while True:
        selection = normalize_user_input(prompt_non_empty("Choose deck (number or exact deck name): ", logger))
        if selection.isdigit():
            index = int(selection)
            if 1 <= index <= len(deck_names):
                return deck_names[index - 1]

        for name in deck_names:
            if selection.lower() == name.lower():
                return name

        logger.warning("Invalid deck selection '%s'. Enter a valid number or deck name.", selection)


def ensure_deck_exists(deck_name, logger):
    deck_names = get_anki_deck_names(logger)
    if not deck_names:
        logger.warning("Could not verify deck existence because deck list is unavailable.")
        return True

    for name in deck_names:
        if deck_name.lower() == name.lower():
            return True

    logger.error("Deck '%s' does not exist in Anki.", deck_name)
    logger.error("Available decks: %s", ", ".join(deck_names))
    return False


def can_add_note(note, logger):
    result = call_anki_connect("canAddNotes", logger, params={"notes": [note]})
    if isinstance(result, list) and len(result) == 1:
        return bool(result[0])
    return None


def find_existing_note_id(deck_name, model_name, kanji, logger):
    escaped_kanji = str(kanji or "").replace('"', '\\"')
    query = f'deck:"{deck_name}" note:"{model_name}" kanji:"{escaped_kanji}"'
    note_ids = call_anki_connect("findNotes", logger, params={"query": query})
    if isinstance(note_ids, list) and note_ids:
        return note_ids[0]
    return None


def update_anki_note_fields(note_id, fields_data, logger):
    result = call_anki_connect(
        "updateNoteFields",
        logger,
        params={
            "note": {
                "id": note_id,
                "fields": fields_data,
            }
        },
    )
    return result is not None


def prompt_duplicate_action(kanji, logger):
    logger.warning("Duplicate note detected for kanji '%s'.", kanji)
    logger.info("Choose how to proceed:")
    logger.info("  s  = skip this note")
    logger.info("  u  = update existing note")
    logger.info("  r  = re-fetch up to 10 dictionary candidates and choose one to add")
    logger.info("  sa = skip this and all remaining duplicates")
    logger.info("  ua = update this and all remaining duplicates")
    return prompt_choice("Your choice [s/u/r/sa/ua]: ", ["s", "u", "r", "sa", "ua"], logger)


def normalize_clause_text(value):
    # Normalize for comparison by removing all whitespace and surrounding quotes.
    return "".join(normalize_user_input(value).split())


def is_clause_mismatch(input_kanji, fetched_expression):
    input_norm = normalize_clause_text(input_kanji)
    fetched_norm = normalize_clause_text(fetched_expression)
    if not input_norm or not fetched_norm:
        return False
    return input_norm != fetched_norm


def prompt_clause_import_choice(input_kanji, fetched_expression, logger):
    logger.warning("Fetched entry does not match full input clause.")
    logger.info("  Input clause : %s", input_kanji)
    logger.info("  Fetched term : %s", fetched_expression)
    logger.info("Choose which version to import:")
    logger.info("  f = fetched dictionary term")
    logger.info("  i = your original input clause (only kanji + vietnamese fields)")
    return prompt_choice("Your choice [f/i]: ", ["f", "i"], logger)


def print_final_result_screen(log_ctx, stats, started_at):
    logger = log_ctx["logger"]
    elapsed = (datetime.datetime.now() - started_at).total_seconds()
    successful_notes = stats["anki_success"] + stats["anki_updated"]
    success_rate = (successful_notes / stats["total_items"] * 100.0) if stats["total_items"] else 0.0

    summary_lines = [
        "",
        "=" * 64,
        "FINAL RESULT",
        "=" * 64,
        f"Items processed      : {stats['total_items']}",
        f"Anki notes created   : {stats['anki_success']}",
        f"Anki notes updated   : {stats['anki_updated']}",
        f"Anki duplicates skip : {stats['anki_skipped']}",
        f"Anki note failures   : {stats['anki_failure']}",
        f"Yomitan hits         : {stats['yomitan_success']}",
        f"Yomitan misses       : {stats['yomitan_failure']}",
        f"Success rate         : {success_rate:.1f}%",
        f"Elapsed time         : {elapsed:.1f}s",
        f"Run logs             : {log_ctx['run_dir']}",
        f"Latest logs          : {log_ctx['latest_dir']}",
        "=" * 64,
        "",
    ]

    summary_text = "\n".join(summary_lines)
    print(summary_text)
    logger.info("Run summary: %s", json.dumps({
        "total_items": stats["total_items"],
        "anki_success": stats["anki_success"],
        "anki_updated": stats["anki_updated"],
        "anki_skipped": stats["anki_skipped"],
        "anki_failure": stats["anki_failure"],
        "yomitan_success": stats["yomitan_success"],
        "yomitan_failure": stats["yomitan_failure"],
        "success_rate": round(success_rate, 1),
        "elapsed_seconds": round(elapsed, 1),
    }, ensure_ascii=False))


def sanitize_filename(value):
    sanitized = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in str(value or ""))
    return sanitized[:80] or "empty"


def write_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_user_input(value):
    return str(value or "").strip().strip('"').strip("'")


def safe_input(message, logger):
    try:
        return input(message)
    except EOFError:
        logger.error("Input stream ended unexpectedly. Exiting.")
        raise SystemExit(1)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user. Exiting.")
        raise SystemExit(130)


def read_text_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def validate_parsed_items(parsed_items):
    if not isinstance(parsed_items, list):
        raise ValueError("Parsed JSON must be a JSON array of objects with 'kanji' and 'vietnamese'.")

    for idx, item in enumerate(parsed_items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Parsed JSON item #{idx} is not an object.")
        if "kanji" not in item or "vietnamese" not in item:
            raise ValueError(f"Parsed JSON item #{idx} must contain 'kanji' and 'vietnamese'.")


def prompt_non_empty(message, logger):
    while True:
        value = safe_input(message, logger).strip()
        if value:
            return value
        logger.warning("Input cannot be empty. Please try again.")


def prompt_choice(message, valid_choices, logger):
    valid = {choice.lower() for choice in valid_choices}
    while True:
        value = normalize_user_input(safe_input(message, logger)).lower()
        if value in valid:
            return value
        logger.warning("Invalid choice '%s'. Valid options: %s", value, ", ".join(sorted(valid)))


def read_multiline_input(logger):
    logger.info("Paste your content below. End input with a single line: EOF")
    lines = []
    while True:
        line = safe_input("", logger)
        if line.strip() == "EOF":
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    if not text:
        logger.warning("No text provided in multiline input.")
    return text


def load_parsed_json(parsed_json_input):
    parsed_json_raw = parsed_json_input
    normalized_input = normalize_user_input(parsed_json_input)
    if os.path.isfile(normalized_input):
        parsed_json_raw = read_text_file(normalized_input)

    parsed_items = json.loads(parsed_json_raw)
    validate_parsed_items(parsed_items)
    return parsed_items, parsed_json_raw


def run_interactive_setup(logger):
    logger.info("No options were provided. Starting interactive setup...")

    deck_name = prompt_deck_name(logger)

    mode = prompt_choice(
        "Choose input mode [1=raw text, 2=parsed json]: ",
        ["1", "2"],
        logger,
    )

    if mode == "1":
        source_mode = prompt_choice(
            "Raw text source [1=file path, 2=paste text]: ",
            ["1", "2"],
            logger,
        )

        if source_mode == "1":
            while True:
                file_path = normalize_user_input(prompt_non_empty("Path to raw text file: ", logger))
                if os.path.isfile(file_path):
                    raw_text = read_text_file(file_path)
                    break
                logger.error("File does not exist: %s", file_path)
        else:
            raw_text = read_multiline_input(logger)
            while not raw_text:
                logger.warning("Raw text cannot be empty.")
                raw_text = read_multiline_input(logger)

        if not os.environ.get("GEMINI_API_KEY"):
            logger.warning("GEMINI_API_KEY is not set.")
            api_key = prompt_non_empty("Enter GEMINI_API_KEY: ", logger)
            os.environ["GEMINI_API_KEY"] = api_key
            logger.info("GEMINI_API_KEY was provided via interactive prompt.")

        return {
            "deck": deck_name,
            "mode": "raw",
            "raw_text": raw_text,
        }

    while True:
        source_mode = prompt_choice(
            "Parsed JSON source [1=file path, 2=paste json]: ",
            ["1", "2"],
            logger,
        )

        if source_mode == "1":
            json_input = normalize_user_input(prompt_non_empty("Path to parsed JSON file: ", logger))
        else:
            json_input = read_multiline_input(logger)

        try:
            parsed_items, parsed_json_raw = load_parsed_json(json_input)
            return {
                "deck": deck_name,
                "mode": "parsed_json",
                "parsed_items": parsed_items,
                "parsed_json_raw": parsed_json_raw,
            }
        except Exception as e:
            logger.error("Invalid parsed JSON input: %s", e)
            logger.info("Please try entering the parsed JSON again.")


def setup_logging_environment():
    script_dir = Path(__file__).resolve().parent
    logs_dir = script_dir / "logs"
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    run_dir = logs_dir / f"run-{timestamp}"
    latest_dir = logs_dir / "latest"
    run_yomitan_dir = run_dir / "yomitan"
    latest_yomitan_dir = latest_dir / "yomitan"
    run_anki_dir = run_dir / "anki"
    latest_anki_dir = latest_dir / "anki"

    for d in [
        logs_dir,
        run_dir,
        latest_dir,
        run_yomitan_dir,
        latest_yomitan_dir,
        run_anki_dir,
        latest_anki_dir,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("batch_anki")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    run_file_handler = logging.FileHandler(run_dir / "pipeline.log", mode="w", encoding="utf-8")
    run_file_handler.setFormatter(formatter)

    latest_file_handler = logging.FileHandler(latest_dir / "pipeline.log", mode="w", encoding="utf-8")
    latest_file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(run_file_handler)
    logger.addHandler(latest_file_handler)

    return {
        "logger": logger,
        "logs_dir": logs_dir,
        "run_dir": run_dir,
        "latest_dir": latest_dir,
        "run_yomitan_dir": run_yomitan_dir,
        "latest_yomitan_dir": latest_yomitan_dir,
        "run_anki_dir": run_anki_dir,
        "latest_anki_dir": latest_anki_dir,
    }

def setup_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
    return genai.Client(api_key=api_key)

def clean_text_with_ai(model, raw_text, log_ctx):
    logger = log_ctx["logger"]
    logger.info("Sending raw text to AI Cleaning Layer...")
    prompt = f"""
    Act as a fuzzy parser for Japanese study notes. Extract the primary Japanese word as 'kanji' 
    and capture the ENTIRE remainder of the line (including typos, vietnamese meanings, and side notes) 
    as the 'vietnamese' field. If there is only the Japanese word then supply the 'vietnamese' field 
    with your interpertation of what the vietnamese meaning for the word is and the postfix " (generated)".
    
    Return ONLY a valid, strict JSON array of objects with 'kanji' and 'vietnamese' keys. No markdown blocks.
    
    Raw Notes:
    {raw_text}
    """

    timer = threading.Timer(
        AI_SLOW_WARNING_SECONDS,
        lambda: logger.warning(
            "AI request is taking longer than expected (> %ss). Still waiting...",
            AI_SLOW_WARNING_SECONDS,
        ),
    )
    timer.daemon = True
    started_at = datetime.datetime.now()
    timer.start()

    try:
        response = model.models.generate_content(
            model=AI_MODEL_NAME,
            contents=prompt,
        )
    except Exception as e:
        logger.exception("AI request failed before response was returned.")
        raise e
    finally:
        timer.cancel()
        elapsed = (datetime.datetime.now() - started_at).total_seconds()
        logger.info("AI request finished in %.1f seconds.", elapsed)

    try:
        response_text = getattr(response, "text", "") or ""
        # Strip potential markdown formatting if the model still includes it
        clean_json = response_text.replace('```json', '').replace('```', '').strip()
        parsed = json.loads(clean_json)

        write_json_file(log_ctx["run_dir"] / "ai_parsed.json", parsed)
        write_json_file(log_ctx["latest_dir"] / "ai_parsed.json", parsed)
        write_json_file(log_ctx["run_dir"] / "ai_raw_response.json", {"raw_response": response_text})
        write_json_file(log_ctx["latest_dir"] / "ai_raw_response.json", {"raw_response": response_text})
        logger.info("Saved AI parsed JSON to logs.")

        return parsed
    except json.JSONDecodeError as e:
        error_payload = {
            "error": "json_decode_error",
            "raw_response": getattr(response, "text", ""),
        }
        write_json_file(log_ctx["run_dir"] / "ai_parsed_error.json", error_payload)
        write_json_file(log_ctx["latest_dir"] / "ai_parsed_error.json", error_payload)
        logger.error("Failed to parse AI output as JSON. Raw response saved to logs.")
        raise e

def fetch_yomitan_data(
    kanji,
    log_ctx,
    item_index,
    max_entries=1,
    markers=None,
    include_media=True,
    log_suffix="",
):
    logger = log_ctx["logger"]
    logger.info("Fetching dictionary data for: %s", kanji)
    effective_markers = markers or ["expression", "pitch-accents", "reading", "glossary-first-brief", "audio"]
    payload = {
        "text": kanji,
        "type": "term",
        "markers": effective_markers,
        "maxEntries": max_entries,
        "includeMedia": include_media,
    }
    
    try:
        response = requests.post(YOMITAN_API_URL, json=payload, timeout=AI_REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as e:
        logger.warning("Yomitan API request failed: %s", e)
        return None
    safe_kanji = sanitize_filename(kanji)
    yomitan_file_name = f"{item_index:03d}_{safe_kanji}{log_suffix}.json"

    if response.status_code != 200:
        error_payload = {
            "kanji": kanji,
            "request": payload,
            "status_code": response.status_code,
            "response_text": response.text,
        }
        write_json_file(log_ctx["run_yomitan_dir"] / yomitan_file_name, error_payload)
        write_json_file(log_ctx["latest_yomitan_dir"] / yomitan_file_name, error_payload)
        logger.warning("Yomitan API returned status code %s. Using fallback data.", response.status_code)
        return None

    yomi_json = response.json()
    write_json_file(log_ctx["run_yomitan_dir"] / yomitan_file_name, yomi_json)
    write_json_file(log_ctx["latest_yomitan_dir"] / yomitan_file_name, yomi_json)
    return yomi_json


def fetch_yomitan_candidates_for_duplicate(kanji, log_ctx, item_index):
    logger = log_ctx["logger"]
    logger.info("Re-fetching candidates for duplicate kanji: %s", kanji)
    return fetch_yomitan_data(
        kanji,
        log_ctx,
        item_index,
        max_entries=10,
        markers=["expression", "reading", "glossary-plain"],
        include_media=False,
        log_suffix="_candidates",
    )


def parse_glossary_plain(glossary_plain):
    raw = str(glossary_plain or "").replace("\\n", "\n")
    pieces = []
    for part in raw.split("<br>"):
        for line in part.splitlines():
            cleaned = line.strip()
            if cleaned:
                pieces.append(cleaned)

    if not pieces:
        return "", []

    source = pieces[0]
    meanings = pieces[1:]
    return source, meanings


def format_glossary_plain_for_anki(glossary_plain):
    source, meanings = parse_glossary_plain(glossary_plain)
    if not source and not meanings:
        return ""
    if not meanings:
        return source

    list_html = "".join(f"<li>{meaning}</li>" for meaning in meanings)
    return f"{source}<ul>{list_html}</ul>"


def prompt_duplicate_candidate_choice(candidates, logger):
    logger.info("Possible dictionary candidates:")
    for i, candidate in enumerate(candidates, start=1):
        expr = candidate.get("expression", "")
        reading = candidate.get("reading", "")
        source = candidate.get("source", "")
        meanings = candidate.get("meanings", [])
        logger.info("  %d) %s [%s]", i, expr, reading)
        if source:
            logger.info("     Source: %s", source)
        if meanings:
            for meaning in meanings:
                logger.info("     - %s", meaning)

    while True:
        selection = normalize_user_input(
            safe_input("Choose candidate number to add (or 's' to skip): ", logger)
        ).lower()
        if selection == "s":
            return None
        if selection.isdigit():
            index = int(selection)
            if 1 <= index <= len(candidates):
                return candidates[index - 1]
        logger.warning("Invalid selection '%s'. Enter a number between 1 and %d, or 's'.", selection, len(candidates))


def choose_duplicate_candidate_fields(base_fields, kanji, log_ctx, item_index):
    logger = log_ctx["logger"]
    yomi_candidates = fetch_yomitan_candidates_for_duplicate(kanji, log_ctx, item_index)
    if not yomi_candidates or not yomi_candidates.get("fields"):
        logger.warning("No candidate entries returned for kanji '%s'.", kanji)
        return None

    candidates = []
    for field in yomi_candidates.get("fields", []):
        expression = field.get("expression", "")
        reading = field.get("reading", "")
        glossary_plain = field.get("glossary-plain", "")
        source, meanings = parse_glossary_plain(glossary_plain)
        candidates.append(
            {
                "expression": expression,
                "reading": reading,
                "source": source,
                "meanings": meanings,
                "formatted_note": format_glossary_plain_for_anki(glossary_plain),
            }
        )

    if not candidates:
        logger.warning("No usable candidate entries returned for kanji '%s'.", kanji)
        return None

    selected = prompt_duplicate_candidate_choice(candidates, logger)
    if not selected:
        return None

    return selected


def resolve_selected_duplicate_candidate(base_fields, selected, kanji, log_ctx, item_index):
    logger = log_ctx["logger"]
    full_yomi_data = fetch_yomitan_data(
        kanji,
        log_ctx,
        item_index,
        max_entries=10,
        log_suffix="_selected_full",
    )
    if not full_yomi_data or not full_yomi_data.get("fields"):
        logger.warning("Could not load full dictionary entries for selected candidate '%s'.", kanji)
        return None

    selected_expression = selected.get("expression", "")
    selected_reading = selected.get("reading", "")
    matched_index = None
    matched_field = None
    for idx, field in enumerate(full_yomi_data.get("fields", [])):
        expression = field.get("expression", "")
        reading = field.get("reading", "")
        if expression == selected_expression and reading == selected_reading:
            matched_index = idx
            matched_field = field
            break

    if matched_field is None:
        logger.warning(
            "Selected candidate not found in full dictionary re-fetch (expression=%s, reading=%s).",
            selected_expression,
            selected_reading,
        )
        return None

    resolved_fields = dict(base_fields)
    resolved_fields["kanji"] = matched_field.get("expression", base_fields.get("kanji", ""))
    resolved_fields["pronunciation"] = matched_field.get("pitch-accents", "")
    resolved_fields["kana"] = matched_field.get("reading", "")
    resolved_fields["note"] = matched_field.get("glossary-first-brief", "")
    resolved_fields["voice"] = matched_field.get("audio", "")

    audio_media = full_yomi_data.get("audioMedia") or []
    if matched_index is not None and matched_index < len(audio_media):
        audio_obj = audio_media[matched_index]
        filename = audio_obj.get("ankiFilename")
        content = audio_obj.get("content")
        if filename and content:
            store_media_in_anki(filename, content, logger)

    return resolved_fields

def store_media_in_anki(filename, base64_data, logger):
    logger.info("Storing audio file %s in Anki media collection...", filename)
    payload = {
        "action": "storeMediaFile",
        "version": 6,
        "params": {
            "filename": filename,
            "data": base64_data
        }
    }
    try:
        response = requests.post(ANKI_CONNECT_URL, json=payload, timeout=AI_REQUEST_TIMEOUT_SECONDS).json()
    except requests.RequestException as e:
        logger.error("Error storing media: %s", e)
        return
    if response.get("error"):
        logger.error("Error storing media: %s", response["error"])

def create_anki_note(deck_name, fields_data, log_ctx, item_index, allow_duplicate=False):
    logger = log_ctx["logger"]
    logger.info("Creating note in deck '%s'...", deck_name)
    payload = {
        "action": "addNote",
        "version": 6,
        "params": {
            "note": {
                "deckName": deck_name,
                "modelName": MODEL_NAME,
                "fields": fields_data,
                "options": {
                    "allowDuplicate": allow_duplicate,
                    "duplicateScope": "deck"
                },
                "tags": ["automated_pipeline"]
            }
        }
    }

    anki_payload_name = f"{item_index:03d}_{sanitize_filename(fields_data.get('kanji'))}.json"
    write_json_file(log_ctx["run_anki_dir"] / anki_payload_name, payload)
    write_json_file(log_ctx["latest_anki_dir"] / anki_payload_name, payload)
    
    try:
        response = requests.post(ANKI_CONNECT_URL, json=payload, timeout=AI_REQUEST_TIMEOUT_SECONDS).json()
    except requests.RequestException as e:
        logger.error("Error creating Anki note request: %s", e)
        response = {"error": str(e), "result": None}
    response_record = {
        "request": payload,
        "response": response,
    }
    write_json_file(log_ctx["run_anki_dir"] / f"{item_index:03d}_{sanitize_filename(fields_data.get('kanji'))}_response.json", response_record)
    write_json_file(log_ctx["latest_anki_dir"] / f"{item_index:03d}_{sanitize_filename(fields_data.get('kanji'))}_response.json", response_record)

    if response.get("error"):
        logger.error("Error creating Anki note: %s", response["error"])
        return False
    else:
        logger.info("Note successfully created! ID: %s", response["result"])
        return True

def main():
    parser = argparse.ArgumentParser(description="Automated Japanese Note to Anki Pipeline")
    parser.add_argument("--deck", help="Target Anki Deck Name (e.g., 'Japanese::Vocab')")
    parser.add_argument(
        "--on-duplicate",
        choices=["skip", "update"],
        help="Behavior when duplicate notes are detected: skip or update existing note.",
    )
    parser.add_argument(
        "--fail-if-deck-missing",
        action="store_true",
        help="Exit with code 2 if the selected deck does not exist in Anki.",
    )
    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument("--input", help="Raw text string or path to a text file containing the notes")
    input_group.add_argument(
        "--parsed-json",
        help="Path to a JSON file OR raw JSON string containing an array of {kanji, vietnamese}. Skips AI cleaning.",
    )
    args = parser.parse_args()

    raw_text = ""

    log_ctx = setup_logging_environment()
    logger = log_ctx["logger"]
    run_started_at = datetime.datetime.now()

    logger.info("Logs initialized under: %s", log_ctx["logs_dir"])

    is_interactive = len(sys.argv) == 1
    if is_interactive:
        runtime_config = run_interactive_setup(logger)
        deck_name = runtime_config["deck"]
        run_mode = runtime_config["mode"]
    else:
        if not args.deck:
            parser.error("--deck is required unless no options are provided (interactive mode).")
        if not args.input and not args.parsed_json:
            parser.error("Provide --input or --parsed-json, or run with no options for interactive mode.")

        deck_name = args.deck
        run_mode = "parsed_json" if args.parsed_json else "raw"

    if not ensure_deck_exists(deck_name, logger):
        if args.fail_if_deck_missing:
            raise SystemExit(2)
        logger.warning("Continuing even though deck validation failed. Use --fail-if-deck-missing to stop instead.")

    # Step 1 & 2: Parse from user JSON OR AI cleaning
    if run_mode == "parsed_json":
        logger.info("Using user-provided parsed JSON. Skipping AI Cleaning Layer.")

        if is_interactive:
            parsed_items = runtime_config["parsed_items"]
            parsed_json_raw = runtime_config["parsed_json_raw"]
        else:
            try:
                parsed_items, parsed_json_raw = load_parsed_json(args.parsed_json)
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON provided in --parsed-json.")
                raise ValueError("--parsed-json must be a valid JSON array.") from e

        with open(log_ctx["run_dir"] / "parsed_json_input_raw.txt", "w", encoding="utf-8") as f:
            f.write(parsed_json_raw)
        with open(log_ctx["latest_dir"] / "parsed_json_input_raw.txt", "w", encoding="utf-8") as f:
            f.write(parsed_json_raw)

        write_json_file(log_ctx["run_dir"] / "ai_parsed.json", parsed_items)
        write_json_file(log_ctx["latest_dir"] / "ai_parsed.json", parsed_items)
    else:
        # Determine if input is a file or a raw string
        if is_interactive:
            raw_text = runtime_config["raw_text"]
        else:
            cli_input = normalize_user_input(args.input)
            raw_text = args.input
            if os.path.isfile(cli_input):
                raw_text = read_text_file(cli_input)

        with open(log_ctx["run_dir"] / "raw_input.txt", "w", encoding="utf-8") as f:
            f.write(raw_text)
        with open(log_ctx["latest_dir"] / "raw_input.txt", "w", encoding="utf-8") as f:
            f.write(raw_text)

        ai_model = setup_gemini()
        parsed_items = clean_text_with_ai(ai_model, raw_text, log_ctx)

    logger.info("Parsed %d item(s) ready for Yomitan/Anki steps.", len(parsed_items))

    stats = {
        "total_items": len(parsed_items),
        "anki_success": 0,
        "anki_updated": 0,
        "anki_skipped": 0,
        "anki_failure": 0,
        "yomitan_success": 0,
        "yomitan_failure": 0,
    }
    if args.on_duplicate:
        duplicate_policy = args.on_duplicate
    else:
        duplicate_policy = "ask" if is_interactive else "skip"

    clause_mismatch_policy = "ask" if is_interactive else "fetched"

    # Step 3 & 4: Dictionary Lookup and Anki Insertion
    for index, item in enumerate(parsed_items, start=1):
        kanji = item.get("kanji")
        vietnamese = item.get("vietnamese")

        logger.info("Processing item %d: kanji=%s", index, kanji)
        
        yomi_data = fetch_yomitan_data(kanji, log_ctx, index)
        if yomi_data:
            stats["yomitan_success"] += 1
        else:
            stats["yomitan_failure"] += 1
        
        # Initialize default fields with AI fallback
        anki_fields = {
            "kanji": kanji,
            "vietnamese": vietnamese,
            "pronunciation": "",
            "kana": "",
            "note": "",
            "voice": ""
        }

        if yomi_data and yomi_data.get("fields"):
            yomi_fields = yomi_data["fields"][0]
            fetched_expression = yomi_fields.get("expression", kanji)
            use_input_only = False

            if is_clause_mismatch(kanji, fetched_expression):
                logger.warning(
                    "Clause mismatch detected for item %d: input='%s', fetched='%s'",
                    index,
                    kanji,
                    fetched_expression,
                )
                if clause_mismatch_policy == "ask":
                    clause_choice = prompt_clause_import_choice(kanji, fetched_expression, logger)
                    if clause_choice == "i":
                        use_input_only = True
                        logger.info("Using original input clause fields only for item %d.", index)
                    else:
                        logger.info("Using fetched dictionary fields for item %d.", index)
                else:
                    logger.info("Non-interactive mode: using fetched dictionary fields for item %d.", index)
            
            if not use_input_only:
                # Map Yomitan outputs to Anki fields.
                anki_fields["kanji"] = fetched_expression
                anki_fields["pronunciation"] = yomi_fields.get("pitch-accents", "")
                anki_fields["kana"] = yomi_fields.get("reading", "")
                anki_fields["note"] = yomi_fields.get("glossary-first-brief", "")
                anki_fields["voice"] = yomi_fields.get("audio", "") # Contains the [sound:...] tag

                # Handle Audio Base64 Extraction and Storage.
                if yomi_data.get("audioMedia") and len(yomi_data["audioMedia"]) > 0:
                    audio_obj = yomi_data["audioMedia"][0]
                    store_media_in_anki(audio_obj["ankiFilename"], audio_obj["content"], logger)

        candidate_note = {
            "deckName": deck_name,
            "modelName": MODEL_NAME,
            "fields": anki_fields,
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck",
            },
            "tags": ["automated_pipeline"],
        }
        can_add = can_add_note(candidate_note, logger)

        if can_add is False:
            action = duplicate_policy
            if duplicate_policy == "ask":
                selection = prompt_duplicate_action(anki_fields.get("kanji"), logger)
                if selection == "sa":
                    duplicate_policy = "skip"
                    action = "skip"
                elif selection == "ua":
                    duplicate_policy = "update"
                    action = "update"
                elif selection == "r":
                    action = "refetch"
                elif selection == "s":
                    action = "skip"
                else:
                    action = "update"

            if action == "update":
                note_id = find_existing_note_id(deck_name, MODEL_NAME, anki_fields.get("kanji"), logger)
                if note_id:
                    updated = update_anki_note_fields(note_id, anki_fields, logger)
                    if updated:
                        logger.info("Updated existing note ID: %s", note_id)
                        stats["anki_updated"] += 1
                    else:
                        logger.error("Failed to update existing note for kanji=%s", anki_fields.get("kanji"))
                        stats["anki_failure"] += 1
                else:
                    logger.error("Duplicate detected but existing note ID was not found for kanji=%s", anki_fields.get("kanji"))
                    stats["anki_failure"] += 1
            elif action == "refetch":
                selected_candidate = choose_duplicate_candidate_fields(
                    anki_fields,
                    anki_fields.get("kanji"),
                    log_ctx,
                    index,
                )
                if not selected_candidate:
                    logger.warning("No candidate selected for duplicate kanji=%s", anki_fields.get("kanji"))
                    stats["anki_skipped"] += 1
                else:
                    selected_fields = resolve_selected_duplicate_candidate(
                        anki_fields,
                        selected_candidate,
                        anki_fields.get("kanji"),
                        log_ctx,
                        index,
                    )
                    if not selected_fields:
                        logger.warning("Selected candidate could not be resolved from full dictionary data.")
                        stats["anki_skipped"] += 1
                        logger.info("%s", "-" * 40)
                        continue

                    logger.info(
                        "Adding selected candidate as a distinct variant (allowing duplicate first field) for kanji=%s.",
                        selected_fields.get("kanji"),
                    )
                    note_created = create_anki_note(
                        deck_name,
                        selected_fields,
                        log_ctx,
                        index,
                        allow_duplicate=True,
                    )
                    if note_created:
                        stats["anki_success"] += 1
                    else:
                        stats["anki_failure"] += 1
            else:
                logger.warning("Skipped duplicate note for kanji=%s", anki_fields.get("kanji"))
                stats["anki_skipped"] += 1
        else:
            note_created = create_anki_note(deck_name, anki_fields, log_ctx, index)
            if note_created:
                stats["anki_success"] += 1
            else:
                stats["anki_failure"] += 1
        logger.info("%s", "-" * 40)

    logger.info("Pipeline completed.")
    print_final_result_screen(log_ctx, stats, run_started_at)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.getLogger("batch_anki").warning("Interrupted by user. Exiting.")
        raise SystemExit(130)