"""Refresh each release's bundled colors.xml and strings.po from xbmc/xbmc when they change."""

from __future__ import annotations

import fnmatch
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent

# shared verbatim between KodiDevKit and kdk; kdk keeps the engine under src/kdk
_LAYOUTS = [(REPO_ROOT, REPO_ROOT / "data"), (REPO_ROOT / "src" / "kdk", REPO_ROOT / "src" / "kdk" / "data")]
PACKAGE_ROOT, DATA_DIR = next(((pkg, data) for pkg, data in _LAYOUTS if (pkg / "libs").is_dir()), _LAYOUTS[0])
DATA_ROOT = DATA_DIR / "kodi"

GITHUB_API = "https://api.github.com/repos/xbmc/xbmc"
GITHUB_RAW = "https://raw.githubusercontent.com/xbmc/xbmc"

FILES = [
    ("system/colors.xml", "colors.xml"),
    ("addons/resource.language.en_gb/resources/strings.po", "strings.po"),
]


def _gh(url: str) -> bytes:
    """Get the URL's body, sent with the environment's GitHub token when there is one."""
    # anonymous calls are limited per IP, and shared CI runners use that up
    headers = {"User-Agent": "kdk-update-kodi-refs"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as r:
        return r.read()


def _resolve_ref(spec: str) -> str:
    """Resolve a github_ref of branch:NAME, release:GLOB or prerelease:GLOB to a git ref."""
    kind, _, value = spec.partition(":")
    if kind == "branch":
        return value
    if kind not in ("release", "prerelease"):
        raise ValueError(
            f"unknown ref kind in {spec!r}; expected branch:<name>, "
            "release:<glob>, or prerelease:<glob>"
        )

    data = json.loads(_gh(f"{GITHUB_API}/releases?per_page=100"))
    candidates = [
        r for r in data
        if fnmatch.fnmatch(r["tag_name"], value)
        and (kind == "prerelease" or not r.get("prerelease"))
    ]
    if not candidates:
        raise RuntimeError(f"no {kind} matched {value!r} in xbmc/xbmc")
    # the releases endpoint lists newest first
    return candidates[0]["tag_name"]


def _load_releases() -> list[dict]:
    """Load the `Addon.RELEASES` entries that declare a `github_ref`."""
    sys.path.insert(0, str(PACKAGE_ROOT.parent))
    addon = importlib.import_module(f"{PACKAGE_ROOT.name}.libs.addon.addon")
    return [r for r in addon.Addon.RELEASES if r.get("github_ref")]


def _refresh_one(release: dict) -> list[str]:
    """Refresh one release's files; the changed ones as paths relative to the repo root."""
    name = release["name"]
    ref_spec = release["github_ref"]
    resolved = _resolve_ref(ref_spec)
    print(f"[{name}] {ref_spec} -> {resolved}")

    target_dir = DATA_ROOT / name
    target_dir.mkdir(parents=True, exist_ok=True)

    changed = []
    for remote_path, local_name in FILES:
        url = f"{GITHUB_RAW}/{resolved}/{remote_path}"
        try:
            content = _gh(url)
        except (HTTPError, URLError) as e:
            # carrying on would ship a release without Kodi-core data
            raise RuntimeError(f"{remote_path}: {e}") from e

        new_hash = hashlib.sha256(content).hexdigest()
        local_path = target_dir / local_name
        old_hash = (
            hashlib.sha256(local_path.read_bytes()).hexdigest()
            if local_path.exists()
            else None
        )

        if new_hash == old_hash:
            print(f"  = {local_name} unchanged")
            continue

        local_path.write_bytes(content)
        rel = local_path.relative_to(REPO_ROOT)
        print(f"  + {rel} updated ({len(content) // 1024} KB)")
        changed.append(str(rel))

    return changed


def main() -> int:
    """Refresh every release with a github_ref; 0 when done, 1 with none, 2 on a failure."""
    releases = _load_releases()
    if not releases:
        print("No releases with `github_ref` configured in Addon.RELEASES", file=sys.stderr)
        return 1

    all_changed: list[str] = []
    for release in releases:
        try:
            all_changed.extend(_refresh_one(release))
        except Exception as e:
            print(f"[{release['name']}] failed: {e}", file=sys.stderr)
            return 2

    print()
    if all_changed:
        print(f"Updated {len(all_changed)} file(s):")
        for path in all_changed:
            print(f"  {path}")
    else:
        print("All snapshots already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
