"""Construit dist/SimpleTask.exe (un seul fichier).  Usage : python build.py"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(ROOT, "assets", "simpletask.ico")


def make_icon():
    """Icône : quatre pastilles aux couleurs des catégories."""
    os.makedirs(os.path.dirname(ICON), exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, size - 8, size - 8), radius=48, fill="#1e1f22")
    colors = ("#d93636", "#2fa84f", "#8a8f98", "#d2691e")
    for i, c in enumerate(colors):
        x, y = 40 + (i % 2) * 96, 40 + (i // 2) * 96
        d.ellipse((x, y, x + 80, y + 80), fill=c)
    img.save(ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])


def build():
    make_icon()
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--noconsole", "--name", "SimpleTask", "--icon", ICON,
        "--add-data", f"{ICON}{os.pathsep}assets",
        "--add-data", f"{os.path.join(ROOT, 'config', 'gemini.json')}{os.pathsep}config",
        "--collect-data", "sv_ttk",
        "--exclude-module", "PIL", "--exclude-module", "unittest",
        "--exclude-module", "pydoc", "--exclude-module", "numpy",
        os.path.join(ROOT, "SimpleTask.pyw"),
    ], cwd=ROOT)
    print("\nExécutable :", os.path.join(ROOT, "dist", "SimpleTask.exe"))


if __name__ == "__main__":
    build()
