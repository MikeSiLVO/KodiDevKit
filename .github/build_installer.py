#!/usr/bin/env python3
"""
Build a self-contained install.py with embedded package data.

Zips the package files (excluding dev-only content), base64-encodes the zip,
and injects it into installer_template.py to produce install.py.

Usage:
    python build_installer.py [version]
"""

from __future__ import annotations

import base64
import io
import sys
import zipfile
from pathlib import Path

EXCLUDE = {
    ".claude", ".git", ".github", ".gitignore", ".python-version",
    ".flake8", ".travis.yml", "pyrightconfig.json", "pyproject.toml",
    "CLAUDE.md", "Debug JSON Health.txt", "tests", "__pycache__",
}


def should_include(rel: Path) -> bool:
    for part in rel.parts:
        if part in EXCLUDE or part.endswith(".pyc"):
            return False
    return True


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "dev"
    root = Path(__file__).resolve().parent.parent
    template_path = Path(__file__).resolve().parent / "installer_template.py"

    # Build zip
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in sorted(root.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(root)
            if not should_include(rel):
                continue
            zf.write(f, str(rel))
            count += 1

    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    print(f"Bundled {count} files, zip size: {len(buf.getvalue()) // 1024} KB")

    # Inject into template
    template = template_path.read_text(encoding="utf-8")
    output = template.replace("__VERSION__", version)
    output = output.replace("__PACKAGE_DATA__", encoded)

    out_path = root / "install.py"
    out_path.write_text(output, encoding="utf-8")
    print(f"Built {out_path} ({len(output) // 1024} KB)")


if __name__ == "__main__":
    main()
