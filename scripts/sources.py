"""Check the Kodi source map: each symbol is still here and each Kodi name it follows exists."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES = Path(__file__).resolve().parent / "sources.json"


def _symbols(path: Path) -> set[str]:
    """Qualified names of the file's classes and functions, plus "<module>"."""
    names = {"<module>"}

    def walk(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(prefix + child.name)
                walk(child, prefix + child.name + ".")

    walk(ast.parse(path.read_text(encoding="utf-8")))
    return names


def _defines(text: str, name: str) -> bool:
    """True when the Kodi source defines a class, function, member or constant of that name."""
    escaped = re.escape(name)
    if "::" in name:
        return re.search(rf"\b{escaped}\s*\(", text) is not None
    pattern = rf"\b{escaped}\s*[(=]|#define\s+{escaped}\b|\bclass\s+{escaped}\b|\b{escaped}::"
    return re.search(pattern, text) is not None


def main() -> int:
    """Check each row against an xbmc clone, upstream/master by default; 1 on a miss, 2 if none."""
    if len(sys.argv) < 2:
        print("usage: sources.py <xbmc clone> [ref]", file=sys.stderr)
        return 2
    clone = sys.argv[1]
    ref = sys.argv[2] if len(sys.argv) > 2 else "upstream/master"
    rows = json.loads(SOURCES.read_text(encoding="utf-8"))
    symbols: dict[str, set[str]] = {}
    texts: dict[str, str] = {}
    missing = []
    for row in rows:
        file, _, symbol = row["symbol"].partition(":")
        path = REPO_ROOT / file
        if file not in symbols:
            symbols[file] = _symbols(path) if path.is_file() else set()
        if symbol not in symbols[file]:
            missing.append(f"{row['symbol']}: not in this repo")
        for entry in row["kodi"]:
            kodi_path, _, name = entry.partition(":")
            if kodi_path not in texts:
                texts[kodi_path] = subprocess.run(["git", "-C", clone, "show", f"{ref}:{kodi_path}"],
                                                  capture_output=True, text=True).stdout
            if not texts[kodi_path]:
                missing.append(f"{row['symbol']}: {kodi_path} not at {ref}")
            elif name and not _defines(texts[kodi_path], name):
                missing.append(f"{row['symbol']}: {name} not in {kodi_path} at {ref}")
    for line in missing:
        print(line)
    print(f"{len(rows)} rows, {len(missing)} missing at {ref}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
