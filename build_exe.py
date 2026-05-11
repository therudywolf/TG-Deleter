"""
Сборка TG Deleter в .exe. Запуск: python build_exe.py
Результат: один файл TGDeleter.exe в корне проекта.
"""
import os
import shutil
import subprocess
import sys

def main():
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)

    try:
        import customtkinter as ctk
        ctk_dir = os.path.dirname(ctk.__file__)
    except Exception:
        print("Установите customtkinter: pip install customtkinter")
        sys.exit(1)

    # Windows: add-data "C:\path\to\customtkinter;customtkinter"
    ctk_data = os.path.join(ctk_dir, "customtkinter") if os.path.basename(ctk_dir) != "customtkinter" else ctk_dir
    # PyInstaller: --add-data=SOURCE:DEST (на Windows SOURCE может содержать ;)
    add_data_arg = f'--add-data={ctk_data}{os.pathsep}customtkinter'

    # onefile → один exe; потом копируем в корень
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "TGDeleter",
        "--distpath", "dist",
        "--specpath", "build",
        "--workpath", "build",
        add_data_arg,
        "--hidden-import", "pyrogram",
        "--hidden-import", "pyrogram.errors",
        "--hidden-import", "pyrogram.enums",
        "--hidden-import", "customtkinter",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "script.py",
    ]

    print("Запуск PyInstaller...")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(r.returncode)
    src = os.path.join(root, "dist", "TGDeleter.exe")
    dst = os.path.join(root, "TGDeleter.exe")
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        print("Готово: TGDeleter.exe в корне проекта")
    else:
        print("Сборка завершена, проверьте dist/TGDeleter.exe")

if __name__ == "__main__":
    main()
