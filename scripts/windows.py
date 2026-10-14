"""Rebuild windows.json and obsolete_windows.json per release: windows.py <xbmc clone> [remote]."""

from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# shared verbatim between KodiDevKit and kdk; kdk keeps the engine under src/kdk
_LAYOUTS = [(REPO_ROOT, REPO_ROOT / "data"), (REPO_ROOT / "src" / "kdk", REPO_ROOT / "src" / "kdk" / "data")]
PACKAGE_ROOT, DATA_DIR = next(((pkg, data) for pkg, data in _LAYOUTS if (pkg / "libs").is_dir()), _LAYOUTS[0])

# oldest first; a release's history is every branch before its own
HISTORY = ["Helix", "Isengard", "Jarvis", "Krypton", "Leia", "Matrix", "Nexus", "Omega"]
CONSTRUCTOR = re.compile(r'(WINDOW_[A-Z0-9_]+),\s*"([A-Za-z0-9_]+\.xml)"')
SKIP = re.compile(r"_(START|END)$|^WINDOW_INVALID$")


class Kodi:
    """One ref of the local clone."""

    def __init__(self, src, ref):
        self.src, self.ref = src, ref

    def git(self, *args):
        """Run git in the clone and return its output."""
        return subprocess.run(["git", "-C", self.src, *args], capture_output=True, text=True).stdout

    def show(self, path):
        """Show one file's text at this ref."""
        return self.git("show", f"{self.ref}:{path}")

    def window_ids(self):
        """Every WINDOW_ constant Kodi defines, with its evaluated id."""
        consts = {}
        for name, expr in re.findall(r"^#define (WINDOW_[A-Z0-9_]+)\s+(.+?)\s*(?://.*)?$",
                                     self.show("xbmc/guilib/WindowIDs.h"), re.M):
            expr = re.sub(r"WINDOW_[A-Z0-9_]+", lambda m: str(consts.get(m.group(0), "None")), expr)
            try:
                consts[name] = int(eval(expr))
            except Exception:
                pass
        return consts

    def window_files(self):
        """Window constant to xml file, from the window constructors."""
        found = {}
        for line in self.git("grep", "-hE", CONSTRUCTOR.pattern, self.ref, "--", "xbmc/*.cpp", "xbmc/*.h").splitlines():
            for const, name in CONSTRUCTOR.findall(line):
                found.setdefault(const, name)
        return found

    def xml_literals(self):
        """Every quoted *.xml name in the source, a superset of the files this ref loads."""
        out = self.git("grep", "-hoE", r'"[A-Za-z0-9_]+\.xml"', self.ref, "--", "xbmc/*")
        return {line.strip('"') for line in out.splitlines()}

    def files_with(self, pattern):
        """Source files at this ref whose text matches the pattern."""
        out = self.git("grep", "-nF", pattern, self.ref, "--", "xbmc/*.cpp")
        return {line.split(":", 2)[1] for line in out.splitlines()}


def resolve(src, remote, spec):
    """Resolve an `Addon.RELEASES` github_ref to a local ref, the newest tag for a glob."""
    kind, _, value = spec.partition(":")
    if kind == "branch":
        return f"{remote}/{value}"
    tags = Kodi(src, "").git("tag", "-l", value, "--sort=-v:refname").split()
    if not tags:
        raise RuntimeError(f"no local tag matches {value!r}; fetch tags first")
    return tags[0]


def build(src, remote, release):
    """Build both window tables for one release and write them to its data folder."""
    kodi = Kodi(src, resolve(src, remote, release["github_ref"]))
    consts = kodi.window_ids()
    translator = kodi.show("xbmc/input/WindowTranslator.cpp")
    names = re.findall(r'\{"([a-z0-9]+)",\s*(WINDOW_[A-Z0-9_]+)\}', translator[:translator.index("FallbackWindowMapping")])

    target = DATA_DIR / release["name"]
    old_rows = json.loads((target / "windows.json").read_text(encoding="utf-8"))
    file_by_id = {}
    for const, fname in kodi.window_files().items():
        if const in consts:
            file_by_id.setdefault(consts[const], fname)
    # a constructor the pattern cannot read keeps the file recorded before
    for _, wid, fname, *_ in old_rows:
        file_by_id.setdefault(wid, fname)

    dialog_ids = {v for k, v in consts.items() if k.startswith("WINDOW_DIALOG_") and not SKIP.search(k)}
    modeless_sources = {f for f in kodi.files_with("MODELESS")
                        if not f.endswith(("GUIDialog.cpp", "ApplicationSkinHandling.cpp"))}
    modeless_sources |= kodi.files_with("CGUIDialog::Open(false")
    modeless_ids = set()
    for path in modeless_sources:
        const = re.search(r"WINDOW_[A-Z_]+", kodi.show(path))
        if const and const.group(0) in consts:
            modeless_ids.add(consts[const.group(0)])

    def kind(wid):
        if wid in modeless_ids:
            return "modeless"
        return "modal" if wid in dialog_ids else "window"

    rows, named = [], set()
    for name, const in names:
        wid = consts[const]
        named.add(wid)
        rows.append([name, wid, file_by_id.get(wid, ""), kind(wid)])
    for const, wid in sorted(consts.items(), key=lambda kv: kv[1]):
        if not SKIP.search(const) and wid not in named:
            rows.append([None, wid, file_by_id.get(wid, ""), kind(wid)])
    (target / "windows.json").write_text("[\n" + ",\n".join("  " + json.dumps(r) for r in rows) + "\n]\n",
                                         encoding="utf-8")

    own = kodi.ref.split("/")[-1]
    history = HISTORY[:HISTORY.index(own)] if own in HISTORY else HISTORY
    if release["github_ref"].startswith("release:"):
        history = HISTORY[:HISTORY.index(release["github_ref"].rsplit("-", 1)[-1])]
    current = kodi.xml_literals()
    obsolete = {}
    for branch in history:
        old = Kodi(src, f"{remote}/{branch}")
        for const, fname in old.window_files().items():
            if fname in current or fname in obsolete:
                continue
            # only a surviving constant says which window took over; a bare id may be reused
            obsolete[fname] = file_by_id.get(consts[const], "") if const in consts else ""
    (target / "obsolete_windows.json").write_text(json.dumps(dict(sorted(obsolete.items())), indent=2) + "\n",
                                                  encoding="utf-8")
    print(f"{release['name']} ({kodi.ref}): {len(rows)} windows, {len(obsolete)} obsolete files")


def main() -> int:
    """Build the window tables of every release; 1 without a clone path."""
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    src, remote = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "upstream"
    sys.path.insert(0, str(PACKAGE_ROOT.parent))
    releases = importlib.import_module(f"{PACKAGE_ROOT.name}.libs.addon.addon").Addon.RELEASES
    for release in releases:
        build(src, remote, release)
    return 0


if __name__ == "__main__":
    sys.exit(main())
