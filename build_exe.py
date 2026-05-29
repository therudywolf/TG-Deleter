
# SPDX-License-Identifier: AGPL-3.0-only
# TG Deleter - Desktop utility for managing Telegram messages
# Copyright (C) 2024-2026 TG Deleter Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Build TG Deleter into a single windowed .exe.

Run: python build_exe.py

Produces TGDeleter.exe in the project root. Regenerates the icon if missing,
bundles the assets folder, and wires the hidden imports pystray/pyrogram need.
Build artifacts land in build/ and dist/ (both gitignored).
"""
import os
import shutil
import subprocess
import sys


def _ensure_icon(root):
    """Generate assets/icon.ico if it is not already present."""
    ico = os.path.join(root, "assets", "icon.ico")
    if os.path.isfile(ico):
        return ico
    gen = os.path.join(root, "assets", "make_icon.py")
    if os.path.isfile(gen):
        print("Icon missing — generating...")
        subprocess.run([sys.executable, gen], check=False)
    return ico if os.path.isfile(ico) else None


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)

    try:
        import customtkinter as ctk
        ctk_dir = os.path.dirname(ctk.__file__)
    except Exception:
        print("Install customtkinter first: pip install -r requirements.txt")
        sys.exit(1)

    ctk_data = ctk_dir if os.path.basename(ctk_dir) == "customtkinter" else os.path.join(ctk_dir, "customtkinter")
    sep = os.pathsep  # ; on Windows, : elsewhere

    icon = _ensure_icon(root)
    assets_dir = os.path.join(root, "assets")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "TGDeleter",
        "--distpath", "dist",
        "--specpath", "build",
        "--workpath", "build",
        f"--add-data={ctk_data}{sep}customtkinter",
    ]
    if os.path.isdir(assets_dir):
        cmd.append(f"--add-data={assets_dir}{sep}assets")
    if icon:
        cmd += ["--icon", icon]
    cmd += [
        "--hidden-import", "pyrogram",
        "--hidden-import", "pyrogram.errors",
        "--hidden-import", "pyrogram.enums",
        "--hidden-import", "customtkinter",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "pystray",
        "--hidden-import", "pystray._win32",
        "--collect-submodules", "pystray",
        "script.py",
    ]

    print("Running PyInstaller...")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(r.returncode)

    src = os.path.join(root, "dist", "TGDeleter.exe")
    dst = os.path.join(root, "TGDeleter.exe")
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        size_mb = os.path.getsize(dst) / (1024 * 1024)
        print(f"Done: TGDeleter.exe in project root ({size_mb:.1f} MB)")
    else:
        print("Build finished — check dist/TGDeleter.exe")


if __name__ == "__main__":
    main()
