# Batch WebP to PNG + Images to PDF Guide

This folder contains two scripts:
- `batch_convert_webp_to_png.py`: converts all `.webp` files from `input/` into `.png` files in `output/`.
- `images-to-pdf.py`: combines image files from `output/` into one PDF file.

## Folder Layout

Expected structure:

```text
batch-webp-to-png/
  batch_convert_webp_to_png.py
  images-to-pdf.py
  input/
  output/
```

## What the scripts do automatically

Both scripts:
- create a local virtual environment in `.venv/` if missing
- install Pillow automatically
- rerun themselves inside that virtual environment

So you can run them directly without manual dependency setup.

## Recommended workflow

1. Put your `.webp` files into `input/`.
2. Run the conversion script.
3. Check generated `.png` files in `output/`.
4. Run the PDF script to create a combined PDF.

## Run commands (PowerShell)

From inside `batch-webp-to-png/`:

```powershell
python .\batch_convert_webp_to_png.py
python .\images-to-pdf.py
```

If `python` is not on PATH, use your launcher (for example `py`).

## Script details

### 1) `batch_convert_webp_to_png.py`

Default configuration:
- `INPUT_FOLDER = "./input"`
- `OUTPUT_FOLDER = "./output"`

Behavior:
- reads all files in `input/`
- converts only files ending in `.webp` (case-insensitive)
- writes `.png` files to `output/`
- creates `output/` if it does not exist

### 2) `images-to-pdf.py`

Default configuration:
- `INPUT_FOLDER = "./output"`
- `OUTPUT_FILE = "combined_images.pdf"`
- supported types: `.png`, `.jpg`, `.jpeg`

Behavior:
- collects supported image files from `output/`
- sorts files alphabetically before creating pages
- converts images to RGB for PDF compatibility
- writes one PDF file: `combined_images.pdf`

## Customization

Open each script and edit the constants near the top.

Common changes:
- use a different input/output folder
- change the PDF filename
- control page order by renaming files in `output/` (alphabetical order is used)

## Troubleshooting

- `No supported image files found...`
  - Make sure `output/` has `.png`, `.jpg`, or `.jpeg` files before running `images-to-pdf.py`.

- `No such file or directory: './input'`
  - Create `input/` in the same folder as the script and add `.webp` files.

- Conversion errors for individual files
  - File may be corrupted or not a valid image. Re-export or replace that source file.

## Notes

- Running `images-to-pdf.py` before conversion is fine, but it will only work if `output/` already has image files.
- The generated `.venv/`, `input/`, and `output/` folders are local artifacts and are typically ignored in git.
