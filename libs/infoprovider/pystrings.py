"""String ids in add-on Python: the one under the cursor, and the wrappers that pass ids along."""

from __future__ import annotations

import ast
import os
import re
import threading
import time
import xml.etree.ElementTree as ET

SOURCE_ADDON = "addon"
SOURCE_KODI = "kodi"

_NUMBER = re.compile(r"\d+")
_CALLEE_BEFORE = re.compile(r"(\.?[A-Za-z_][\w.]*)\s*$")
_ADDON_MACRO = re.compile(r"\$ADDON\[\s*([\w.\-]+)\s+(\d+)\s*\]")
_LOCALIZE_MACRO = re.compile(r"\$LOCALIZE\[\s*(\d+)\s*\]")
_SKIP_DIRS = {"__pycache__", "venv", "node_modules"}
_MAX_FILE_BYTES = 1_000_000
_RECHECK_SECONDS = 2.0
_LOOKUP = "getLocalizedString"


def lookup_source(callee):
    """Which strings a direct getLocalizedString call reads, or None for any other call."""
    if callee.rsplit(".", 1)[-1] != _LOOKUP:
        return None
    # xbmc.getLocalizedString reads Kodi's tables; Addon().getLocalizedString only the add-on's
    return SOURCE_KODI if callee in ("xbmc." + _LOOKUP, _LOOKUP) else SOURCE_ADDON


def _enclosing_callee(line, pos):
    """Callee text of the innermost call whose first argument holds the position, or None."""
    depth = 0
    for i in range(pos - 1, -1, -1):
        ch = line[i]
        if ch in ")]}":
            depth += 1
        elif ch in "([{":
            if depth:
                depth -= 1
                continue
            if ch != "(":
                return None
            m = _CALLEE_BEFORE.search(line, 0, i)
            return m.group(1) if m else None
        elif ch == "," and not depth:
            return None
    return None


def label_at(line, col, source_of):
    """The string id under the cursor as (addon id or None, label id, source), or None."""
    for pattern, has_addon in ((_ADDON_MACRO, True), (_LOCALIZE_MACRO, False)):
        for m in pattern.finditer(line):
            if m.start() <= col <= m.end():
                if has_addon:
                    return m.group(1), m.group(2), SOURCE_ADDON
                return None, m.group(1), SOURCE_KODI

    for m in _NUMBER.finditer(line):
        if not m.start() <= col <= m.end():
            continue
        before = line[m.start() - 1] if m.start() else ""
        after = line[m.end()] if m.end() < len(line) else ""
        if before.isalnum() or before in "_." or after.isalpha() or after in "_.":
            return None
        callee = _enclosing_callee(line, m.start())
        source = source_of(callee) if callee else None
        return (None, m.group(0), source) if source else None
    return None


def _callee_text(node):
    """Dotted text of a call target such as `self.addon.getLocalizedString`, or None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append("")
    else:
        return None
    return ".".join(reversed(parts))


def _passes_param(call, param):
    """True when the call's first argument is the param, bare or through int()."""
    if not call.args:
        return False
    arg = call.args[0]
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "int":
        arg = arg.args[0] if arg.args else arg
    return isinstance(arg, ast.Name) and arg.id == param


def _first_param(args, is_method):
    """Name of the first parameter a caller fills, past self or cls; None when there is none."""
    names = [a.arg for a in args.posonlyargs + args.args]
    if is_method and names and names[0] in ("self", "cls"):
        names = names[1:]
    return names[0] if names else None


def _forwarded_calls(body_nodes, param):
    """Callee texts of every call in the body that takes the param as its first argument."""
    found = []
    if not param:
        return found
    for node in body_nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and _passes_param(sub, param):
                text = _callee_text(sub.func)
                if text:
                    found.append(text)
    return found


def _assigned_calls(value):
    """Callee texts a lambda or bound-method alias forwards to."""
    if isinstance(value, ast.Lambda):
        return _forwarded_calls([value.body], _first_param(value.args, False))
    if isinstance(value, ast.Attribute):
        text = _callee_text(value)
        return [text] if text else []
    return []


class FileFacts:
    """What one Python file says about wrappers: its own names, its methods and its imports."""

    def __init__(self, source_text):
        self.names = {}
        self.attrs = {}
        self.imports = {}
        self.stars = []
        try:
            tree = ast.parse(source_text)
        except (SyntaxError, ValueError):
            return
        self._collect(tree, in_class=False)

    def _collect(self, node, in_class):
        """Collect one scope's defs and aliases, as names or, inside classes, as attrs."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not (child.name.startswith("__") and child.name.endswith("__")):
                    calls = _forwarded_calls(child.body, _first_param(child.args, in_class))
                    if calls:
                        table = self.attrs if in_class else self.names
                        table.setdefault(child.name, []).extend(calls)
                self._collect(child, in_class=False)
            elif isinstance(child, ast.ClassDef):
                self._collect(child, in_class=True)
            elif isinstance(child, ast.Assign):
                calls = _assigned_calls(child.value)
                for target in child.targets if calls else ():
                    if isinstance(target, ast.Name):
                        table = self.attrs if in_class else self.names
                        table.setdefault(target.id, []).extend(calls)
                    elif isinstance(target, ast.Attribute):
                        self.attrs.setdefault(target.attr, []).extend(calls)
            elif isinstance(child, ast.Import):
                for a in child.names:
                    top = a.name.split(".")[0]
                    self.imports[a.asname or top] = (a.name if a.asname else top, 0, None)
            elif isinstance(child, ast.ImportFrom):
                for a in child.names:
                    if a.name == "*":
                        self.stars.append((child.module or "", child.level))
                    else:
                        self.imports[a.asname or a.name] = (child.module or "", child.level, a.name)
            else:
                self._collect(child, in_class)


class Resolver:
    """Wrapper sources across a set of files, resolving each call as Python would from its file."""

    def __init__(self, facts):
        self.facts = facts
        self._by_suffix = {}
        for path in facts:
            parts = os.path.splitext(path.replace("\\", "/"))[0].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):
                self._by_suffix.setdefault(".".join(parts[i:]), path)
        self.names = {}
        self.attrs = {}
        self._settle()

    def _module_file(self, path, module, level):
        """File a module name imported from the path points at, or None when it is not scanned."""
        if level:
            base = os.path.dirname(path)
            for _ in range(level - 1):
                base = os.path.dirname(base)
            rel = os.path.join(base, *module.split(".")) if module else base
            for candidate in (rel + ".py", os.path.join(rel, "__init__.py")):
                if candidate in self.facts:
                    return candidate
            return None
        return self._by_suffix.get(module)

    def _imported(self, path, local):
        """Where a name imported into the file comes from, as (file or None, name or None)."""
        module, level, real = self.facts[path].imports[local]
        if real is None:
            return self._module_file(path, module, level), None
        sub = self._module_file(path, f"{module}.{real}" if module else real, level)
        if sub:
            return sub, None
        return self._module_file(path, module, level), real

    def source(self, path, callee):
        """Which strings a call written in the file reads, or None when it is no string lookup."""
        direct = lookup_source(callee)
        if direct:
            return direct
        parts = callee.split(".")
        if len(parts) == 1:
            return self._bare(path, parts[0], set())
        facts = self.facts.get(path)
        if len(parts) == 2 and facts and parts[0] in facts.imports:
            target, real = self._imported(path, parts[0])
            if target and real is None:
                return self.names.get((target, parts[1]))
        return self.attrs.get(parts[-1])

    def _bare(self, path, name, seen):
        """Source of a bare name as the file sees it: its own def, an import, or a star import."""
        facts = self.facts.get(path)
        if not facts or path in seen:
            return None
        seen.add(path)
        if name in facts.names:
            return self.names.get((path, name))
        if name in facts.imports:
            target, real = self._imported(path, name)
            return self._bare(target, real, seen) if target and real else None
        for module, level in facts.stars:
            target = self._module_file(path, module, level)
            found = self._bare(target, name, seen) if target else None
            if found:
                return found
        return None

    def _settle(self):
        """Settle every candidate against the others until nothing changes."""
        pending = [(path, name, calls, False) for path, f in self.facts.items()
                   for name, calls in f.names.items()]
        pending += [(path, name, calls, True) for path, f in self.facts.items()
                    for name, calls in f.attrs.items()]
        for _ in range(len(pending) + 1):
            changed = False
            for path, name, calls, is_attr in pending:
                table, key = (self.attrs, name) if is_attr else (self.names, (path, name))
                sources = {self.source(path, callee) for callee in calls} - {None}
                sources.add(table.get(key))
                sources.discard(None)
                # a wrapper reaching both tables shows every source, as a Kodi lookup does
                source = SOURCE_ADDON if sources == {SOURCE_ADDON} else SOURCE_KODI if sources else None
                if source and table.get(key) != source:
                    table[key] = source
                    changed = True
            if not changed:
                break


def dependency_roots(addon_path):
    """Library folders of the Python modules the add-on imports, found beside it on disk."""
    roots = []
    try:
        requires = list(ET.parse(os.path.join(addon_path, "addon.xml")).getroot().iter("import"))
    except (ET.ParseError, OSError):
        return roots
    addons_dir = os.path.dirname(os.path.normpath(addon_path))
    for node in requires:
        dep = node.get("addon") or ""
        if dep.startswith("xbmc."):
            continue
        dep_path = os.path.join(addons_dir, dep)
        try:
            dep_root = ET.parse(os.path.join(dep_path, "addon.xml")).getroot()
        except (ET.ParseError, OSError):
            continue
        for ext in dep_root.iter("extension"):
            if ext.get("point") == "xbmc.python.module":
                roots.append(os.path.join(dep_path, ext.get("library") or ""))
    return roots


class WrapperIndex:
    """Wrappers across one add-on and its Python dependencies, rebuilt in the background."""

    def __init__(self, root, extra_roots=()):
        self.root = root
        self.extra_roots = list(extra_roots)
        self._lock = threading.Lock()
        self._files = {}
        self._resolver = Resolver({})
        self._checked = 0.0
        self._refreshing = False

    def resolver(self):
        """The current resolver, at once; starts a background refresh when it may be stale."""
        with self._lock:
            stale = time.monotonic() - self._checked > _RECHECK_SECONDS
            start = stale and not self._refreshing
            if start:
                self._refreshing = True
            current = self._resolver
        if start:
            threading.Thread(target=self._refresh, daemon=True).start()
        return current

    def refresh(self):
        """Refresh now, reparsing only the Python files that changed."""
        with self._lock:
            self._refreshing = True
        self._refresh()

    def _refresh(self):
        """Background body of a refresh; always clears the in-progress flag."""
        try:
            files = {}
            for path, mtime, own in self._python_files():
                cached = self._files.get(path)
                if cached and cached[0] == mtime:
                    files[path] = cached
                    continue
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    continue
                # a dependency file counts only when it calls getLocalizedString itself
                files[path] = (mtime, FileFacts(text) if own or _LOOKUP in text else None)
            resolver = Resolver({p: facts for p, (_, facts) in files.items() if facts})
            with self._lock:
                self._files = files
                self._resolver = resolver
        finally:
            with self._lock:
                self._checked = time.monotonic()
                self._refreshing = False

    def _python_files(self):
        """Yield (path, mtime, own) for each .py file to scan, skipping hidden and vendor dirs."""
        for root, own in [(self.root, True)] + [(r, False) for r in self.extra_roots]:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS]
                for name in filenames:
                    if not name.endswith(".py"):
                        continue
                    path = os.path.join(dirpath, name)
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    if st.st_size <= _MAX_FILE_BYTES:
                        yield path, st.st_mtime, own
