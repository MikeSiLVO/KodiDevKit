"""Refresh bundled Kodi reference snapshots from upstream xbmc/xbmc.

For each release listed in `Addon.RELEASES`, fetch the latest `colors.xml` and
`strings.po` matching its `github_ref` and write them to the package's
`data/kodi/<release>/`. Compares SHA256 first; only writes on change.

Snapshots are committed, so this runs only when refreshing them. Requires no
extra Python deps - uses `urllib`.
"""

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

# The engine lives at <root>/libs in KodiDevKit and <root>/src/kdk/libs in kdk;
# this script is shared verbatim, so find the layout rather than assume one.
_LAYOUTS = [(REPO_ROOT, REPO_ROOT / "data"), (REPO_ROOT / "src" / "kdk", REPO_ROOT / "src" / "kdk" / "data")]
PACKAGE_ROOT, DATA_DIR = next(((pkg, data) for pkg, data in _LAYOUTS if (pkg / "libs").is_dir()), _LAYOUTS[0])
DATA_ROOT = DATA_DIR / "kodi"

GITHUB_API = "https://api.github.com/repos/xbmc/xbmc"
GITHUB_RAW = "https://raw.githubusercontent.com/xbmc/xbmc"

# Files to fetch from each ref. (remote_path, local_filename).
FILES = [
    ("system/colors.xml", "colors.xml"),
    ("addons/resource.language.en_gb/resources/strings.po", "strings.po"),
]


def _gh(url: str) -> bytes:
    # Anonymous callers get 60 requests/hour per IP, which shared CI runners
    # burn through, so use a token when one is in the environment.
    headers = {"User-Agent": "kdk-update-kodi-refs"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as r:
        return r.read()


def _resolve_ref(spec: str) -> str:
    """Resolve a `github_ref` spec to a concrete git ref usable in raw URLs.

    Supported syntax:
      branch:<name>      - that branch's HEAD
      release:<glob>     - latest non-prerelease release tag matching glob
      prerelease:<glob>  - latest release tag matching glob (allows prereleases)
    """
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
    # Releases endpoint returns most-recent first.
    return candidates[0]["tag_name"]


def _load_releases() -> list[dict]:
    """Return `Addon.RELEASES` entries that declare a `github_ref`."""
    sys.path.insert(0, str(PACKAGE_ROOT.parent))
    addon = importlib.import_module(f"{PACKAGE_ROOT.name}.libs.addon.addon")
    return [r for r in addon.Addon.RELEASES if r.get("github_ref")]


def _refresh_one(release: dict) -> list[str]:
    """Fetch `release`'s files; return list of changed local paths (relative to DATA_ROOT)."""
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
            # Continuing here would ship a release with no Kodi-core data.
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
