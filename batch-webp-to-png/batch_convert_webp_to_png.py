import os
import subprocess
import sys
import venv
from pathlib import Path

# --- Configuration ---
INPUT_FOLDER = "./input"   # Folder containing your .webp files
OUTPUT_FOLDER = "./output" # Folder where .png files will be saved
VENV_FOLDER = ".venv"


def _in_virtual_environment():
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _venv_python_path(venv_path):
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _install_dependencies(python_executable):
    subprocess.check_call([python_executable, "-m", "pip", "install", "Pillow"])


def ensure_virtual_environment():
    script_dir = Path(__file__).resolve().parent
    venv_path = script_dir / VENV_FOLDER

    if _in_virtual_environment():
        try:
            import PIL  # noqa: F401
        except ImportError:
            print("Installing required dependency: Pillow")
            _install_dependencies(sys.executable)
        return

    if not venv_path.exists():
        print(f"Creating virtual environment at: {venv_path}")
        venv.EnvBuilder(with_pip=True).create(venv_path)

    venv_python = _venv_python_path(venv_path)
    print("Installing required dependency: Pillow")
    _install_dependencies(str(venv_python))

    # Re-run this script from the virtual environment.
    os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])


def batch_convert_webp_to_png():
    from PIL import Image

    # 1. Create the output folder if it doesn't exist
    Path(OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)

    # 2. Keep track of how many files we convert
    success_count = 0

    # 3. Loop through all files in the input folder
    for filename in os.listdir(INPUT_FOLDER):
        if filename.lower().endswith(".webp"):
            input_path = os.path.join(INPUT_FOLDER, filename)
            
            # Create the new filename by replacing .webp with .png
            output_filename = filename.rsplit('.', 1)[0] + ".png"
            output_path = os.path.join(OUTPUT_FOLDER, output_filename)
            
            # 4. Open, convert, and save the image
            try:
                with Image.open(input_path) as img:
                    # PNG supports transparency just like WebP, so we can save it directly
                    img.save(output_path, "PNG")
                    print(f"Converted: {filename} -> {output_filename}")
                    success_count += 1
            except Exception as e:
                print(f"Error converting {filename}: {e}")

    print(f"\nDone! Successfully converted {success_count} files.")

if __name__ == "__main__":
    ensure_virtual_environment()
    batch_convert_webp_to_png()