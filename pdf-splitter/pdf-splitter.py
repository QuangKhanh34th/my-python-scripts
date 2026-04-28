import os
import subprocess
import sys
import venv
from pathlib import Path

INPUT_FOLDER = Path(__file__).resolve().parent / "input"
VENV_FOLDER = ".venv"


def _in_virtual_environment():
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _venv_python_path(venv_path):
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _install_dependencies(python_executable):
    subprocess.check_call([python_executable, "-m", "pip", "install", "pypdf"])


def normalize_user_input(value):
    return str(value or "").strip().strip('"').strip("'")


def safe_input(message):
    try:
        return input(message)
    except EOFError:
        print("Input stream ended unexpectedly. Exiting.")
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("Interrupted by user. Exiting.")
        raise SystemExit(130)


def prompt_non_empty(message):
    while True:
        value = safe_input(message).strip()
        if value:
            return value
        print("Input cannot be empty. Please try again.")


def list_input_pdfs():
    INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    return sorted(
        [
            file_path
            for file_path in INPUT_FOLDER.iterdir()
            if file_path.is_file() and file_path.suffix.lower() == ".pdf"
        ]
    )


def prompt_pdf_selection(pdf_files):
    print("Available PDF files:")
    for index, file_path in enumerate(pdf_files, start=1):
        print(f"  {index}) {file_path.name}")

    while True:
        selection = normalize_user_input(prompt_non_empty("Choose file (number or exact file name): "))
        if selection.isdigit():
            index = int(selection)
            if 1 <= index <= len(pdf_files):
                return pdf_files[index - 1]

        for file_path in pdf_files:
            if selection.lower() == file_path.name.lower():
                return file_path

        print(f"Invalid file selection '{selection}'. Enter a valid number or file name.")


def resolve_input_pdf(input_argument=None):
    if input_argument:
        candidate_path = Path(normalize_user_input(input_argument))
        if candidate_path.is_file():
            return candidate_path

        input_candidate = INPUT_FOLDER / candidate_path.name
        if input_candidate.is_file():
            return input_candidate

        raise FileNotFoundError(f"The file '{input_argument}' does not exist.")

    pdf_files = list_input_pdfs()
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files were found in '{INPUT_FOLDER}'.")

    if len(pdf_files) == 1:
        return pdf_files[0]

    return prompt_pdf_selection(pdf_files)


def ensure_virtual_environment():
    script_dir = Path(__file__).resolve().parent
    venv_path = script_dir / VENV_FOLDER

    if _in_virtual_environment():
        try:
            import pypdf  # noqa: F401
        except ImportError:
            print("Installing required dependency: pypdf")
            _install_dependencies(sys.executable)
        return

    if not venv_path.exists():
        print(f"Creating virtual environment at: {venv_path}")
        venv.EnvBuilder(with_pip=True).create(venv_path)

    venv_python = _venv_python_path(venv_path)
    print("Installing required dependency: pypdf")
    _install_dependencies(str(venv_python))

    # Re-run this script from the virtual environment.
    script_path = str(Path(__file__).resolve())
    completed = subprocess.run([str(venv_python), script_path, *sys.argv[1:]], check=False)
    raise SystemExit(completed.returncode)

ensure_virtual_environment()

from pypdf import PdfReader, PdfWriter

# --- 2. Main PDF Splitting Logic ---
def split_pdf(input_pdf_path):
    # Check if the file exists
    if not os.path.exists(input_pdf_path):
        print(f"Error: The file '{input_pdf_path}' does not exist.")
        sys.exit(1)

    # Setup naming and output directory
    base_name = os.path.splitext(os.path.basename(input_pdf_path))[0]
    output_dir = f"{base_name}_pages"
    
    # Create a folder to hold all the individual pages
    os.makedirs(output_dir, exist_ok=True)

    try:
        reader = PdfReader(input_pdf_path)
        total_pages = len(reader.pages)
        
        print(f"Found {total_pages} pages in '{input_pdf_path}'.")
        print(f"Splitting into folder: '{output_dir}/'...")

        # Loop through every page and save it as a new PDF
        for i in range(total_pages):
            writer = PdfWriter()
            writer.add_page(reader.pages[i])

            # Name files with 1-based indexing (e.g., document_page_1.pdf)
            output_filename = os.path.join(output_dir, f"{base_name}_page_{i + 1}.pdf")
            
            with open(output_filename, "wb") as output_pdf:
                writer.write(output_pdf)
                
            # Optional: Print progress for large PDFs
            # print(f"Saved page {i + 1}/{total_pages}")

        print(f"\nSuccess! Extracted {total_pages} single-page PDFs.")
        
    except Exception as e:
        print(f"An error occurred while processing the PDF: {e}")

if __name__ == "__main__":
    try:
        pdf_file = resolve_input_pdf(sys.argv[1] if len(sys.argv) >= 2 else None)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print(f"Place PDF files in '{INPUT_FOLDER}' or pass a valid file path.")
        sys.exit(1)

    split_pdf(str(pdf_file))