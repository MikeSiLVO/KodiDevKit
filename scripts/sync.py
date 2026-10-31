"""Mirror the shared engine from KodiDevKit, the canonical copy, into kdk, or check it still is."""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

SHARED_LIB_DIRS = ("addon", "infoprovider", "polib", "reporting", "skin", "utils", "validation")

SHARED_LIB_FILES = ("__init__.py", "coredata.py")

SHARED_DATA = ("kodi_builtin_controls.xml",)
SHARED_DATA_DIRS = ("omega", "piers", "kodi/omega", "kodi/piers", "addon_schema")

SHARED_SCRIPTS = ("refresh.py", "windows.py")

# each repo's own front end: same path in both trees, different on purpose
FRONTEND = {
    "libs/infoprovider/loader.py",
    "libs/infoprovider/provider.py",
    "libs/reporting/text.py",
}

# never leaves KodiDevKit: needs Sublime, mdpopups or the live-Kodi client
EDITOR_ONLY = {
    "libs/sublime", "libs/kodi",
    "libs/infoprovider/tooltips.py", "libs/infoprovider/navigation.py",
    "libs/infoprovider/pystrings.py",
    "libs/reporting/html.py", "libs/reporting/server.py",
    "libs/utils/decorators.py",
}

EDITOR_ONLY_TESTS = {
    "run_tests.py", "test_hover.py",
    "test_negation_twin_filter.py", "test_report_filtering.py",
    "test_include_param_roles.py", "test_pystrings.py", "test_report_picker.py", "test_builtin.py",
    "test_report_server.py",
}

# --apply skips these files whole; move a divergence into a FRONTEND file where possible
EXEMPT: dict[str, set[str]] = {}


class StripDocs(ast.NodeTransformer):
    """Transformer dropping docstrings, leaving only the logic to compare."""

    def _strip(self, node):
        """Strip the node's docstring after visiting its children."""
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


def _bound_names(node) -> list[str]:
    """Plain names this statement assigns, empty for anything else."""
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def units(path: Path) -> dict[str, str]:
    """Comparable pieces of the file by qualified name, as source without docstrings."""
    try:
        tree = StripDocs().visit(ast.parse(path.read_text(encoding="utf-8")))
    except (OSError, SyntaxError):
        return {}
    out: dict[str, str] = {}

    def walk(node, prefix=""):
        # statements binding no plain name still change behavior; compare them as one lump
        residual = []
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefix + child.name] = ast.unparse(child)
            elif isinstance(child, ast.ClassDef):
                walk(child, prefix + child.name + ".")
            elif names := _bound_names(child):
                # whitelists and severity constants drift as readily as code
                for name in names:
                    out[prefix + name] = ast.unparse(child)
            else:
                residual.append(ast.unparse(child))
        if residual:
            label = "<module prelude>" if not prefix else f"<{prefix.rstrip('.')} body>"
            out[label] = "\n".join(residual)

    walk(tree)
    return out


def find_kdk(explicit: str | None) -> Path:
    """Find kdk: the path given, KDK_ROOT, a sibling kdk folder or /mnt/c/kdk; exit when none is."""
    for candidate in (explicit, os.environ.get("KDK_ROOT"),
                      str(HERE.parent / "kdk"), "/mnt/c/kdk"):
        if candidate and (Path(candidate) / "src" / "kdk" / "libs").is_dir():
            return Path(candidate)
    sys.exit("Could not locate the kdk checkout; pass --kdk or set KDK_ROOT.")


def pairs(kdk: Path):
    """Yield (label, canonical path, kdk path) for every file that mirrors."""
    for fname in SHARED_LIB_FILES:
        src = HERE / "libs" / fname
        if src.is_file():
            yield f"libs/{fname}", src, kdk / "src" / "kdk" / "libs" / fname
    for fname in SHARED_DATA:
        src = HERE / "data" / fname
        if src.is_file():
            yield f"data/{fname}", src, kdk / "src" / "kdk" / "data" / fname
    for fname in SHARED_SCRIPTS:
        src = HERE / "scripts" / fname
        if src.is_file():
            yield f"scripts/{fname}", src, kdk / "scripts" / fname
    for sub in SHARED_DATA_DIRS:
        for src in sorted((HERE / "data" / sub).glob("*")):
            if src.is_file():
                rel = f"data/{sub}/{src.name}"
                yield rel, src, kdk / "src" / "kdk" / rel
    for name in SHARED_LIB_DIRS:
        for src in sorted((HERE / "libs" / name).rglob("*.py")):
            rel = src.relative_to(HERE).as_posix()
            if "__pycache__" in rel:
                continue
            if rel in FRONTEND:
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
    """Check every mirrored file and print a summary; 1 on drift or a missing file, else 0."""
    drifted, missing, exempt_ok, textonly, clean = [], [], 0, 0, 0
    for rel, src, dst in pairs(kdk):
        if not dst.exists():
            missing.append(rel)
            continue
        if src.read_bytes() == dst.read_bytes():
            clean += 1
            continue
        if src.suffix != ".py":
            drifted.append((rel, ["<file contents>"]))
            continue
        a, b = units(src), units(dst)
        differing = {n for n in set(a) & set(b) if a[n] != b[n]} | (set(a) ^ set(b))
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
        auto = [r for r, _ in drifted if r not in EXEMPT] + missing
        manual = [r for r, _ in drifted if r in EXEMPT]
        print()
        if auto:
            print(f"`--apply` fixes {len(auto)}: " + ", ".join(auto))
        if manual:
            print(f"`--apply` will NOT touch {len(manual)} (declared divergent); port by hand "
                  "or widen the entry in EXEMPT: " + ", ".join(manual))
        return 1
    return 0


def apply(kdk: Path) -> int:
    """Apply the mirror, copying each changed file into kdk, then confirm kdk still imports."""
    copied = 0
    for rel, src, dst in pairs(kdk):
        if rel in EXEMPT:
            continue
        if dst.exists() and src.read_bytes() == dst.read_bytes():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  {rel} -> {dst.relative_to(kdk)}")
        copied += 1
    print(f"{copied} file(s) mirrored" if copied else "already in sync")
    if EXEMPT:
        print(f"{len(EXEMPT)} file(s) hold exempt symbols and were skipped; port those by hand.")
    return _verify_importable(kdk)


def _verify_importable(kdk: Path) -> int:
    """Verify kdk's engine imports, in a subprocess; 1 when the mirror broke it."""
    import subprocess
    probe = ("import importlib, pkgutil, sys; sys.path.insert(0, %r); import kdk.libs; "
             "[importlib.import_module(m.name) "
             "for m in pkgutil.walk_packages(kdk.libs.__path__, 'kdk.libs.')]" % str(kdk / "src"))
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    if result.returncode:
        print("\nMirror left kdk unimportable:")
        print("  " + (result.stderr.strip().splitlines() or ["?"])[-1])
        return 1
    print("kdk imports cleanly after mirroring.")
    return 0


def main() -> int:
    """Run --check or --apply against the kdk checkout found."""
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
