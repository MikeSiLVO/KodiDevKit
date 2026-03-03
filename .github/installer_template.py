#!/usr/bin/env python3
"""
KodiDevKit Installer

Installs KodiDevKit into Sublime Text's Packages directory.
Detects OS and Sublime Text installation automatically.

Usage:
    python install.py
    python install.py --uninstall
"""

from __future__ import annotations

import base64
import io
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PACKAGE_NAME = "KodiDevKit"
VERSION = "__VERSION__"
PACKAGE_DATA = "__PACKAGE_DATA__"


def get_packages_paths() -> list[Path]:
    system = platform.system()
    paths = []
    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            paths.append(Path(appdata) / "Sublime Text" / "Packages")
            paths.append(Path(appdata) / "Sublime Text 3" / "Packages")
    elif system == "Darwin":
        home = Path.home()
        paths.append(home / "Library" / "Application Support" / "Sublime Text" / "Packages")
        paths.append(home / "Library" / "Application Support" / "Sublime Text 3" / "Packages")
    else:
        home = Path.home()
        paths.append(home / ".config" / "sublime-text" / "Packages")
        paths.append(home / ".config" / "sublime-text-3" / "Packages")
        paths.append(home / "snap" / "sublime-text" / "current" / ".config" / "sublime-text" / "Packages")
        paths.append(home / ".var" / "app" / "com.sublimetext.three" / "config" / "sublime-text-3" / "Packages")
    return paths


def find_packages_dir() -> Path | None:
    for path in get_packages_paths():
        if path.is_dir():
            return path
    return None


def has_package_control(packages_dir: Path) -> bool:
    if (packages_dir / "Package Control").is_dir():
        return True
    installed = packages_dir.parent / "Installed Packages" / "Package Control.sublime-package"
    return installed.is_file()


def extract_embedded(packages_dir: Path) -> bool:
    dest = packages_dir / PACKAGE_NAME
    print("  Extracting package ...")
    try:
        raw = base64.b64decode(PACKAGE_DATA)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            dest.mkdir(parents=True, exist_ok=True)
            for info in zf.infolist():
                if info.is_dir():
                    (dest / info.filename).mkdir(parents=True, exist_ok=True)
                else:
                    target = dest / info.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(target, "wb") as dst:
                        dst.write(src.read())
        return True
    except Exception as e:
        print(f"  Extraction failed: {e}")
        return False


def uninstall(packages_dir: Path) -> bool:
    dest = packages_dir / PACKAGE_NAME
    if not dest.exists():
        print(f"  {PACKAGE_NAME} is not installed.")
        return False
    is_repo = (dest / ".git").exists()
    if is_repo:
        print(f"  WARNING: {dest} is a git repository.")
        print("  If you are developing KodiDevKit, consider removing it manually.")
        print()
        resp = input("  Delete this repository? (y/N): ").strip().lower()
        if resp != "y":
            print("  Cancelled.")
            return False
    print(f"  Removing {dest} ...")
    shutil.rmtree(dest)
    print(f"  {PACKAGE_NAME} has been removed.")
    return True


def main():
    is_uninstall = "--uninstall" in sys.argv

    print()
    print(f"  KodiDevKit {'Uninstaller' if is_uninstall else 'Installer'} (v{VERSION})")
    print(f"  {'=' * 40}")
    print()

    # Find Sublime Text
    print("  Looking for Sublime Text ...")
    packages_dir = find_packages_dir()

    if packages_dir is None:
        print()
        print("  Could not find Sublime Text Packages directory.")
        print()
        print("  Expected locations:")
        for p in get_packages_paths():
            print(f"    {p}")
        print()
        print("  If Sublime Text is installed in a custom location,")
        print("  create the Packages directory and run this installer again.")
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    print(f"  Found: {packages_dir}")
    print()

    if is_uninstall:
        uninstall(packages_dir)
        input("\n  Press Enter to exit ...")
        return

    # Check existing install
    dest = packages_dir / PACKAGE_NAME
    if dest.exists():
        print(f"  {PACKAGE_NAME} is already installed at:")
        print(f"    {dest}")
        print()

        is_repo = (dest / ".git").exists()
        if is_repo:
            print("  WARNING: This is a git repository.")
            try:
                result = subprocess.run(
                    ["git", "-C", str(dest), "status", "--porcelain"],
                    capture_output=True, text=True,
                )
                if result.stdout.strip():
                    print("  It has UNCOMMITTED CHANGES that will be lost!")
                result = subprocess.run(
                    ["git", "-C", str(dest), "log", "--oneline", "@{u}..HEAD"],
                    capture_output=True, text=True,
                )
                if result.stdout.strip():
                    print("  It has UNPUSHED COMMITS that will be lost!")
            except (FileNotFoundError, subprocess.CalledProcessError):
                print("  Could not check repository status.")
            print()
            print("  If you are developing KodiDevKit, do NOT reinstall.")
            print("  Use 'git pull' to update instead.")
            print()
            resp = input("  Delete this repository and reinstall? (y/N): ").strip().lower()
        else:
            resp = input("  Reinstall? (y/N): ").strip().lower()

        if resp != "y":
            print("  Cancelled.")
            input("\n  Press Enter to exit ...")
            return
        print("  Removing existing installation ...")
        shutil.rmtree(dest)
        print()

    # Check Package Control
    if not has_package_control(packages_dir):
        print("  WARNING: Package Control is not installed.")
        print("  KodiDevKit needs Package Control for its dependencies")
        print("  (lxml, mdpopups, etc).")
        print()
        print("  To install Package Control:")
        print("    1. Open Sublime Text")
        print("    2. Menu: Tools > Install Package Control...")
        print("    3. Restart Sublime Text")
        print()
        resp = input("  Continue anyway? (y/N): ").strip().lower()
        if resp != "y":
            print("  Cancelled.")
            input("\n  Press Enter to exit ...")
            return
        print()

    # Install
    success = extract_embedded(packages_dir)

    if not success:
        print()
        print("  Installation failed.")
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    print()
    print("  Installation complete!")
    print()
    print("  Next steps:")
    print("    1. Restart Sublime Text")
    has_pc = has_package_control(packages_dir)
    if not has_pc:
        print("    2. Install Package Control (Tools > Install Package Control...)")
        print("    3. Restart Sublime Text again")
    n = 2 if has_pc else 4
    print(f"    {n}. Open your Kodi skin/addon folder as a Sublime Text project")
    print(f"    {n + 1}. Configure settings: Preferences > Package Settings > KodiDevKit")
    print()
    input("  Press Enter to exit ...")


if __name__ == "__main__":
    main()
