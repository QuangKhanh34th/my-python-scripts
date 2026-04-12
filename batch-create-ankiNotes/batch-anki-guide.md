# Batch Create Anki Notes

Automates a Japanese study pipeline:

1. Read raw notes (or pre-parsed, [formatted JSON](#parsed-json-format)).
2. Optionally clean/parse notes with Gemini.
3. Query Yomitan local API for dictionary fields and audio.
4. Create notes in Anki via AnkiConnect.
5. Save detailed logs and payloads for every run.

## Features

- Interactive mode (run with no arguments).
- CLI mode for automation.
- Accepts either:
  - Raw text input (file path or inline text), or
  - Parsed JSON array of `{ "kanji": "...", "vietnamese": "..." }`.
- Quote-tolerant Windows path input in interactive prompts.
- Graceful cancel handling (`Ctrl+C`) in interactive mode.
- Interactive deck picker from Anki deck list (choose by number or name).
- Duplicate strategy controls (skip or update existing note).
- Per-run and latest logs under `logs/`.

## Requirements
### System requirements
- Windows (tested in this repo workflow).
- Python 3.10+
- Gemini API key in `GEMINI_API_KEY` (required only for raw-text mode).

### Anki requirements
- Anki desktop running with AnkiConnect add-on downloaded and enabled (default: `http://127.0.0.1:8765`). 
- Browser extension Yomitan installed
- Yomitan local API running (default: `http://127.0.0.1:19633/ankiFields`).


## Installation
### Installing prerequisites
1. Install Anki
2. install and enable the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) addon
3. Install the browser extension [Yomitan](https://yomitan.wiki/)
4. Follow [Yomitan API installation guide](https://github.com/yomidevs/yomitan-api/blob/master/README.md)
5. Set up required note type for this script
6. [Download](https://github.com/Ookicat/BatchCreateAnkiNote/archive/refs/heads/main.zip) and unzip this repository
7. Run `run-script.bat` and follow the instructions  

### Setting up the Anki Note Type (JPD316)

Before running the script, you must create the specific Note Type (`JPD316`) in Anki that this pipeline expects.

**Step 1: Create the Note Type**

1. Open Anki and click **Tools** > **Manage Note Types** (or press `Ctrl+Shift+N`).
2. Click **Add** > select **Add: Basic** > click **OK**.
3. Name it exactly: `JPD316` and click **OK**.
4. Close the "Choose Note Type" window, but keep the "Note Types" window open.

**Step 2: Add the Required Fields**

1. Select `JPD316` from your Note Types list and click **Fields...**.
2. Rename the default `Front` and `Back` fields, and add new ones until your list matches these exactly (case-sensitive):
* `kanji`
* `pronunciation`
* `kana`
* `vietnamese`
* `voice`
* `note`


3. Click **Save**.

**Step 3: Configure the Card Template**

1. Back on the Note Types window, select `JPD316` and click **Cards...**.
2. In the **Front Template** box, paste the following:

```html
{{kanji}}
```

3. In the **Back Template** box, paste the following:

```html
{{FrontSide}}

<br>
<hr style="height:3px;border:none;color:#000;background-color:#000;">
<br>
{{pronunciation}}
<hr style="height:3px;border:none;color:#000;background-color:#000;">

{{kana}} <br>
{{vietnamese}}
<br>
{{voice}}
<br>

{{note}}

```

4. Click **Save** and close the Note Types window. Your Anki is now ready for the pipeline!


## Quick Start

From project root:

```bat
run-script.bat
```

or click the run-script.bat in the project folder

What `run-script.bat` does:

- Creates `.venv` if missing.
- Installs required packages (`requests`, `google-genai`).
- Activates the environment and runs `batch-anki.py`.

## Usage

### 1) Interactive Mode

Run with no arguments:

```bat
run-script.bat
```

You will be prompted for:

- Deck name
- Input mode:
  - `1` raw text
  - `2` parsed JSON
- Source type:
  - file path (get from "copy file path" option or CTRL + SHIFT + C on the file)
  - pasted content 

Multiline paste mode ends when you enter a line containing exactly:

```text
EOF
```

### 2) CLI Mode (Raw Text)

Using a file path:

```bat
run-script.bat --deck "Japanese::Vocab" --input "notes.txt"
```

Using inline text:

```bat
run-script.bat --deck "Japanese::Vocab" --input "様子 means appearance"
```

### 3) CLI Mode (Parsed JSON)

Using a JSON file:

```bat
run-script.bat --deck "Japanese::Vocab" --parsed-json "parsed.json"
```

Using inline JSON:

```bat
run-script.bat --deck "Japanese::Vocab" --parsed-json "[{\"kanji\":\"様子\",\"vietnamese\":\"tình trạng\"}]"
```

### 4) CLI Flags

Duplicate behavior:

- `--on-duplicate skip`: skip duplicates (safe for batch automation)
- `--on-duplicate update`: update existing notes instead of skipping

Deck validation behavior:

- `--fail-if-deck-missing`: exit immediately with code `2` if deck does not exist

Examples:

```bat
run-script.bat --deck "Japanese::Vocab" --input "notes.txt" --on-duplicate skip
```

```bat
run-script.bat --deck "Japanese::Vocab" --parsed-json "parsed.json" --on-duplicate update
```

```bat
run-script.bat --deck "Japanese::MissingDeck" --input "notes.txt" --fail-if-deck-missing
```

If `--on-duplicate` is not provided:

- Interactive mode defaults to asking per duplicate (`s`, `u`, `r`, `sa`, `ua`).
- Non-interactive mode defaults to `skip`.

In interactive duplicate prompt, `r` means: re-fetch up to 10 Yomitan candidates with markers `expression`, `reading`, and `glossary-plain`, then choose one candidate to add.

## Parsed JSON Format

Expected shape:

```json
[
  {
    "kanji": "様子",
    "vietnamese": "tình trạng"
  },
  {
    "kanji": "緊急",
    "vietnamese": "khẩn cấp"
  }
]
```

Validation rules:

- Top-level must be a JSON array.
- Every item must be an object.
- Every object must contain both `kanji` and `vietnamese` keys.

You can ask chatGPT or any generative AI model to convert your note into this format, using the following prompt or your own prompt if your note format is different from mine:

Example note:
```
宅地 đất ở/làm nhà
自宅 nhà riêng (lịch sự cho 家)
帰宅 về nhà
住宅 nhà ở (dùng khi mua nhà)

当時 đương thời (lúc đó, tại thời điểm đó)
当事 đương sự (Vấn đề đang quan tâm)
当日 ngày hôm đó
当駅 ga đó
本当 sự thật (thật sự, really)
正当 đúng đắn
相当 tương đương, khá là

管理 quản lý
管区 khu vực quản lý
食管 ???
```

The prompt:
> Act as a fuzzy parser for Japanese study notes. Extract the primary Japanese word as 'kanji' and capture the ENTIRE remainder of the line (including typos, vietnamese meanings, and side notes) as the 'vietnamese' field. If there is only the Japanese word then supply the 'vietnamese' field with your interpertation of what the vietnamese meaning for the word is and the postfix " (generated)".
>    
> Return ONLY a valid, strict JSON array of objects with 'kanji' and 'vietnamese' keys.
    
## Environment Variables

- `GEMINI_API_KEY`: Required when using raw text mode.

In interactive raw-text mode, if `GEMINI_API_KEY` is not set, the script prompts for it.

## Model and Field Mapping

- Gemini model: `gemini-2.5-flash`.
- Anki note model name: `JPD316`.

Yomitan fields map to Anki fields as follows:

- `expression` -> `kanji`
- `pitch-accents` -> `pronunciation`
- `reading` -> `kana`
- `glossary-first-brief` -> `note`
- `audio` -> `voice`

If Yomitan lookup fails, script falls back to AI-derived `kanji`/`vietnamese` and leaves other fields empty.

## Logs and Artifacts

Logs are written to:

- `logs/run-YYYYMMDD-HHMMSS/` (per run)
- `logs/latest/` (most recent run snapshot)

Common artifacts:

- `pipeline.log`
- `raw_input.txt` or `parsed_json_input_raw.txt`
- `ai_parsed.json`
- `ai_raw_response.json`
- `yomitan/*.json`
- `anki/*.json` and `anki/*_response.json`

## Troubleshooting

### FutureWarning about `google.generativeai`

This project now uses `google-genai`. If you still see old warnings, recreate venv or run dependency install again.

### "File does not exist" for a valid Windows path

Quoted paths are supported now. Both of these should work in prompts:

- `D:\Programs\Python\scripts\batch-create-ankiNotes\notes.txt`
- `"D:\Programs\Python\scripts\batch-create-ankiNotes\notes.txt"`

### Anki note creation fails

Check:

- Anki is open.
- AnkiConnect addon is installed/enabled.
- `ANKI_CONNECT_URL` matches your local setup.
- Deck and model (`JPD316`) exist in Anki.

If you want strict validation in scripts/CI, add `--fail-if-deck-missing`.

### Yomitan data missing

Check:

- Yomitan local API is running.
- `YOMITAN_API_URL` port/path is correct.

### Gemini errors

Check:

- `GEMINI_API_KEY` is set and valid.
- Internet/API access is available.
- Review `logs/latest/ai_raw_response.json` for model output.

## Project Files

- `batch-anki.py`: Main pipeline script.
- `run-script.bat`: Bootstrap + run helper for Windows.
- `notes.txt`: Optional local source notes.
- `logs/`: Generated run artifacts.

## License

No license file is currently defined in this project root.