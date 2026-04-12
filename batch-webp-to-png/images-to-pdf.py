import os
import subprocess
import sys
import venv
from pathlib import Path

# --- Configuration ---
INPUT_FOLDER = "./output"        # Folder containing your image files
OUTPUT_FILE = "combined_images.pdf" # The name of the resulting PDF
VENV_FOLDER = ".venv"
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


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


def batch_png_to_pdf():
    from PIL import Image

    # 1. Gather all supported image files and sort them (to ensure correct page order)
    input_path = Path(INPUT_FOLDER)
    image_files = sorted(
        [
            f
            for f in input_path.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
    )

    if not image_files:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        print(f"No supported image files ({supported}) found in {INPUT_FOLDER}")
        return

    print(f"Found {len(image_files)} images. Starting conversion...")

    # 2. Open images and convert them to RGB
    # PDF conversion in Pillow requires the images to be in RGB mode 
    # (PNGs are often RGBA, which can cause issues with PDF saving).
    image_list = []
    
    for file in image_files:
        img = Image.open(file)
        # Convert to RGB for Pillow PDF compatibility across all source formats.
        if img.mode != "RGB":
            img = img.convert("RGB")
        image_list.append(img)

    # 3. Save the first image and append the rest as subsequent pages
    if image_list:
        first_image = image_list[0]
        others = image_list[1:]
        
        try:
            first_image.save(
                OUTPUT_FILE, 
                "PDF", 
                resolution=100.0, 
                save_all=True, 
                append_images=others
            )
            print(f"Successfully created: {OUTPUT_FILE}")
        except Exception as e:
            print(f"Error creating PDF: {e}")
        finally:
            # Clean up: close all image objects
            for img in image_list:
                img.close()

if __name__ == "__main__":
    ensure_virtual_environment()
    batch_png_to_pdf()