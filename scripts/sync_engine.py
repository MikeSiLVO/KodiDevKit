"""Mirror the shared validation engine from KodiDevKit into kdk, and verify it stayed mirrored.

KodiDevKit is canonical. kdk vendors the same `libs/` tree and the same test
suite, minus the parts that only make sense inside the editor.

    python scripts/sync_engine.py --check   # report drift, non-zero on unexpected drift
    python scripts/sync_engine.py --apply   # copy canonical -> kdk

Point it at the other tree with --kdk or KDK_ROOT; it defaults to a sibling
checkout next to this one, then /mnt/c/kdk.

Divergence that is deliberate lives in EXEMPT below. Anything else in a mirrored
file is drift, which is what forked these two trees before.
"""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

# libs/<name> in KodiDevKit  ->  src/kdk/libs/<name> in kdk
SHARED_LIB_DIRS = ("addon", "infoprovider", "polib", "reporting", "skin", "utils", "validation")

# Never leaves KodiDevKit: needs Sublime, mdpopups, or the live-Kodi client.
EDITOR_ONLY = {
    "libs/sublime", "libs/kodi",
    "libs/infoprovider/tooltips.py", "libs/infoprovider/navigation.py",
    "libs/reporting/html.py", "libs/reporting/server.py",
    "libs/utils/sublime_helpers.py", "libs/utils/decorators.py",
}

# Test modules covering editor-only features; the rest of tests/ mirrors.
EDITOR_ONLY_TESTS = {
    "run_tests.py",
    "test_extract_expression_at_offset.py", "test_hover_condition.py",
    "test_negation_twin_filter.py", "test_report_filtering.py",
    "test_split_top_level_commas.py", "test_include_param_roles.py",
}

# Re-export modules whose contents track what each tree actually ships. Function
# comparison can't see a differing `from .x import y`, so these are never copied.
NEVER_COPY = {
    "libs/utils/__init__.py",
    "libs/reporting/__init__.py",
    "libs/polib/__init__.py",
}

# Mirrored files that legitimately differ, and the symbols allowed to differ.
# Adding an entry is a decision; a symbol appearing here that isn't listed is drift.
EXEMPT = {
    "libs/infoprovider/checker.py": {
        # kdk filters already-computed results so its GUI toggle is instant.
        "CheckerMixin.get_check_listitems",
    },
    "libs/infoprovider/loader.py": {
        # sublime.load_resource for packaged installs, with a filesystem fallback.
        "LoaderMixin.init_addon", "LoaderMixin.load_data",
    },
    "libs/infoprovider/provider.py": {
        # Different mixin sets, which is the point of the split.
        "InfoProvider.__init__",
    },
    "libs/reporting/text.py": {
        "generate_text_report", "_describe_filters", "issue_visible",
    },
    "libs/skin/skin.py": {
        # Jump-to-definition data with no kdk consumer.
        "Skin.__init__", "Skin.update_include_list",
        "Skin._build_include_param_roles", "Skin.include_param_roles", "Skin.resolve_param_role",
    },
    "libs/utils/expressions.py": {
        "_kodi_macro_mask", "_KEYWORD_MACRO_RE",
        "extract_expression_at_offset", "split_top_level_commas",
    },
    "libs/utils/files.py": {"get_sublime_path"},
    "libs/utils/infobool.py": {
        "negation_of", "probe_booleans", "read_probe", "_PERMISSION_GATED",
        "STATE_TRUE", "STATE_FALSE", "STATE_OFFLINE",
    },
}


class StripDocs(ast.NodeTransformer):
    """Drop docstrings so comparison sees logic, not prose."""

    def _strip(self, node):
        self.generic_visit(node)
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:] or [ast.Pass()]
        return node

    visit_FunctionDef = _strip
    visit_AsyncFunctionDef = _strip
    visit_ClassDef = _strip
    visit_Module = _strip


def units(path: Path) -> dict[str, str]:
    """Qualified name -> normalized source for every function in `path`."""
    try:
        tree = StripDocs().visit(ast.parse(path.read_text(encoding="utf-8")))
    except (OSError, SyntaxError):
        return {}
    out: dict[str, str] = {}

    def walk(node, prefix=""):
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefix + child.name] = ast.unparse(child)
            elif isinstance(child, ast.ClassDef):
                walk(child, prefix + child.name + ".")
            elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                # Whitelists and severity constants drift as readily as code.
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        out[prefix + t.id] = ast.unparse(child)

    walk(tree)
    return out


def find_kdk(explicit: str | None) -> Path:
    for candidate in (explicit, os.environ.get("KDK_ROOT"),
                      str(HERE.parent / "kdk"), "/mnt/c/kdk"):
        if candidate and (Path(candidate) / "src" / "kdk" / "libs").is_dir():
            return Path(candidate)
    sys.exit("Could not locate the kdk checkout; pass --kdk or set KDK_ROOT.")


def pairs(kdk: Path):
    """(relative label, canonical path, kdk path) for everything that mirrors."""
    for name in SHARED_LIB_DIRS:
        for src in sorted((HERE / "libs" / name).rglob("*.py")):
            rel = src.relative_to(HERE).as_posix()
            if "__pycache__" in rel:
                continue
            if any(rel == e or rel.startswith(e + "/") for e in EDITOR_ONLY):
                continue
            yield rel, src, kdk / "src" / "kdk" / rel
    for src in sorted((HERE / "tests").glob("*.py")):
        if src.name in EDITOR_ONLY_TESTS:
            continue
        rel = src.relative_to(HERE).as_posix()
        yield rel, src, kdk / rel


def check(kdk: Path) -> int:
    drifted, missing, exempt_ok, textonly, clean = [], [], 0, 0, 0
    for rel, src, dst in pairs(kdk):
        if not dst.exists():
            missing.append(rel)
            continue
        if src.read_bytes() == dst.read_bytes():
            clean += 1
            continue
        a, b = units(src), units(dst)
        differing = {n for n in set(a) & set(b) if a[n] != b[n]} | (set(a) ^ set(b))
        if rel in NEVER_COPY:
            exempt_ok += 1
            continue
        allowed = EXEMPT.get(rel, set())
        unexpected = differing - allowed
        if unexpected:
            drifted.append((rel, sorted(unexpected)))
        elif differing:
            exempt_ok += 1
        else:
            textonly += 1

    print(f"byte-identical: {clean}   logic-identical (text differs): {textonly}   "
          f"declared-divergent: {exempt_ok}   DRIFT: {len(drifted)}   missing: {len(missing)}")
    for rel in missing:
        print(f"  MISSING in kdk: {rel}")
    for rel, names in drifted:
        print(f"  DRIFT {rel}")
        for n in names:
            print(f"      {n}")
    if drifted or missing:
        print("\nRun `python scripts/sync_engine.py --apply`, or add a deliberate "
              "divergence to EXEMPT in this script.")
        return 1
    return 0


def apply(kdk: Path) -> int:
    copied = 0
    for rel, src, dst in pairs(kdk):
        if rel in EXEMPT or rel in NEVER_COPY:
            continue
        if dst.exists() and src.read_bytes() == dst.read_bytes():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  {rel} -> {dst.relative_to(kdk)}")
        copied += 1
    print(f"{copied} file(s) mirrored" if copied else "already in sync")
    skipped = len(EXEMPT) + len(NEVER_COPY)
    print(f"{skipped} file(s) skipped as deliberately divergent; port those by hand.")
    return _verify_importable(kdk)


def _verify_importable(kdk: Path) -> int:
    """Import kdk's engine in a subprocess; a mirror that breaks it must fail loudly."""
    import subprocess
    probe = ("import sys; sys.path.insert(0, %r); "
             "import kdk.libs.skin.skin, kdk.libs.infoprovider.provider, "
             "kdk.libs.validation, kdk.libs.utils" % str(kdk / "src"))
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    if result.returncode:
        print("\nMirror left kdk unimportable:")
        print("  " + (result.stderr.strip().splitlines() or ["?"])[-1])
        return 1
    print("kdk imports cleanly after mirroring.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report drift without writing")
    ap.add_argument("--apply", action="store_true", help="copy canonical files into kdk")
    ap.add_argument("--kdk", help="path to the kdk checkout")
    args = ap.parse_args()
    if args.check == args.apply:
        ap.error("pass exactly one of --check or --apply")
    kdk = find_kdk(args.kdk)
    print(f"canonical: {HERE}\nkdk:       {kdk}\n")
    return check(kdk) if args.check else apply(kdk)


if __name__ == "__main__":
    sys.exit(main())
