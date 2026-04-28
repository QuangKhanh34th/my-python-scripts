# PDF Splitter Guide

This folder contains a single script:
- `pdf-splitter.py`: splits a PDF into one-page PDFs and writes them into a folder named after the source file.

## Folder Layout

Expected structure:

```text
pdf-splitter/
  pdf-splitter.py
  pdf-splitter-guide.md
  input/
```

## What the script does automatically

The script:
- creates a local virtual environment in `.venv/` if missing
- installs `pypdf` automatically
- reruns itself inside that virtual environment
- accepts either a direct PDF path or a PDF placed in `input/`
- shows numbered choices when multiple PDFs are found in `input/`

## Recommended workflow

1. Put one or more `.pdf` files into `input/`.
2. Run the script.
3. If there is more than one PDF, choose the file by number or exact file name.
4. Check the generated folder named `<pdf-name>_pages/`.

## Run commands

From inside `pdf-splitter/`:

**powershell**
```
python .\pdf-splitter.py
```

**batch**
```
python pdf-splitter.py
```

Or pass a specific file path directly:

**PowerShell**
```
python .\pdf-splitter.py .\input\my_document.pdf
```

**Command Prompt**
```
python pdf-splitter.py input\my_document.pdf
```

If `python` is not on PATH, use your launcher (for example `py`).

## Script details

### `pdf-splitter.py`

Default behavior:
- looks for PDF files in `input/` when no path is provided
- auto-selects the only PDF if there is just one
- prompts for a numbered choice if there are multiple PDFs
- accepts an explicit PDF path from the command line
- creates an output folder named after the source file, such as `my_document_pages/`
- writes one single-page PDF per page in the source document

## Customization

Open `pdf-splitter.py` and edit the constants near the top if you want to change:
- the input folder name
- the virtual environment folder name
- the output folder naming pattern

## Troubleshooting

- `No PDF files were found in '.../input'`
  - Make sure the `input/` folder exists and contains at least one `.pdf` file.

- `The file '...' does not exist`
  - Confirm the file path is correct, or place the PDF inside `input/` and run the script again.

- `Failed to install dependencies`
  - Make sure you have internet access and that Python can create a local virtual environment.

## Notes

- The generated `.venv/`, `input/`, and output folders are local artifacts and are typically ignored in git.
- The script preserves page order from the source PDF when splitting.
