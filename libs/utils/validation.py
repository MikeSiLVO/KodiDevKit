"""Issue building, id normalizing, and the lookups the checks share."""

import os
import re
import logging
from functools import lru_cache

from .expressions import resolve_params_in_text

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def is_runtime_generated_file(file_path):
    """True when the file is one an addon writes at runtime, so its contents are not the skin's."""
    if not file_path:
        return False

    filename = os.path.basename(file_path).lower()

    return filename.startswith('script-skinvariables-')


def normalize_control_id(control_id):
    """Strip leading zeros from a numeric id, since Kodi reads ids as ints; others pass through."""
    if not control_id or not isinstance(control_id, str):
        return control_id

    if not control_id.isdigit():
        return control_id

    normalized = control_id.lstrip('0') or '0'
    return normalized


def create_issue(message, file="", line=0, **kwargs):
    """Create an issue dict with the standard fields plus any extras."""
    issue = {
        "message": message,
        "file": file,
        "line": line,
    }
    issue.update(kwargs)
    return issue


_PARAM_PATTERN = re.compile(r'\$PARAM\[([^\]]+)\]')


def resolve_param_in_name(name, param_context=None, cache=None):
    """Resolve $PARAM in a name from the context, emptying unknown ones."""
    if not name or "$PARAM[" not in name:
        return name

    cache_key = None
    if cache is not None:
        cache_key = (name, frozenset(param_context.items()) if param_context else frozenset())
        if cache_key in cache:
            return cache[cache_key]

    def replace_param(match):
        param_name = match.group(1)
        if param_context and param_name in param_context:
            return param_context[param_name]
        return ''

    resolved = _PARAM_PATTERN.sub(replace_param, name)

    if cache is not None and cache_key is not None:
        cache[cache_key] = resolved

    return resolved


class CallContexts:
    """Param sets the folder's include calls pass, forwarded $PARAM filled from outer calls."""

    def __init__(self, addon, folder):
        if not addon._include_usages_built:
            addon.index_builder.build_include_usages()
        self.usages = addon.include_usages.get(folder, {})
        self._includes = getattr(addon, "include_map", {}).get(folder, {})
        self._filled = {}

    def for_include(self, name, depth=0):
        """Param sets the include is called with, its defaults applied; empty when never called."""
        if name not in self._filled:
            self._filled[name] = []
            defaults = self._includes[name][1] if name in self._includes else {}
            for usage in self.usages.get(name, []):
                for context in self.expand(usage, depth):
                    self._filled[name].append({**defaults, **context})
        return self._filled[name]

    def expand(self, usage, depth=0):
        """Expand a call's params per outer param set, dropping a lone undefined $PARAM."""
        params, outer = usage["params"], usage.get("enclosing")
        if not outer or depth >= _FORWARD_DEPTH or not any("$PARAM[" in v for v in params.values()):
            return [params]
        # a lone undefined $PARAM drops the <param>, leaving the include's default
        return [{k: resolve_param_in_name(v, context) for k, v in params.items()
                 if resolve_params_in_text(v, context)[1] != "SINGLE_UNDEFINED"}
                for context in self.for_include(outer, depth + 1)] or [params]


def get_all_parameter_contexts(addon, folder):
    """Get every param set the folder's includes take, filling forwarded $PARAM from outer calls."""
    calls = CallContexts(addon, folder)
    seen = set()
    all_contexts = []
    for usages in calls.usages.values():
        for usage in usages:
            for context in calls.expand(usage):
                key = frozenset(context.items())
                if key not in seen:
                    seen.add(key)
                    all_contexts.append(context)
    all_contexts.append({})
    return all_contexts


_FORWARD_DEPTH = 5


_GENERATED_INCLUDE_FILE = re.compile(r'^script-.*-includes\.xml$', re.I)


def _kept_location(addon, folder, kind, name):
    """File and line of the definition Kodi kept for the name, or None."""
    if kind == "include":
        node, _params, path = addon.include_map[folder][name]
    elif kind in ("variable", "default"):
        table = addon.variable_map if kind == "variable" else addon.default_map
        node, path = table[folder][name]
    else:
        table = addon.constant_source_map if kind == "constant" else addon.expression_source_map
        return table[folder].get(name)
    return path, getattr(node, "sourceline", 0) or 0


def shadowed_issues(addon, folder, kinds):
    """Issues for the definitions of those kinds Kodi drops: later duplicates, bodiless includes."""
    issues = []
    optional = getattr(addon, "conditional_files", {}).get(folder, set())
    for entry in getattr(addon, "shadowed_defs", {}).get(folder, []):
        kind, name = entry["kind"], entry["name"]
        if kind not in kinds:
            continue
        if kind == "include without definition":
            message = f"Include '{name}' has <param> but no <definition>, so Kodi ignores it"
        else:
            kept = _kept_location(addon, folder, kind, name)
            # a conditional or generated file overriding another is deliberate, not a duplicate
            sources = [entry["file"]] + ([kept[0]] if kept else [])
            if any(p in optional or _GENERATED_INCLUDE_FILE.match(os.path.basename(p))
                   for p in sources):
                continue
            where = f" ({os.path.basename(kept[0])}:{kept[1]})" if kept else ""
            message = f"Duplicate {kind} '{name}': Kodi uses the first definition{where}"
        issues.append(create_issue(message, file=entry["file"], line=entry["line"],
                                   type=kind, name=name, severity="error"))
    return issues


def reference_issues(addon, folder, kind, refs, definitions, defined=(), skip=None):
    """Issues for references to undefined names and for definitions nothing references."""
    cache = {}
    contexts = None

    def param_names(raw):
        nonlocal contexts
        if "$PARAM[" not in raw:
            return []
        if contexts is None:
            contexts = get_all_parameter_contexts(addon, folder)
        return [resolve_param_in_name(raw, context, cache) for context in contexts]

    label = kind.capitalize()
    known = {d["name"] for d in definitions} | set(defined)
    referenced = set()
    issues = []
    for ref in refs:
        name = ref["name"]
        raw = ref.get("raw_name", name)
        resolved = param_names(raw)
        referenced.update(n for n in resolved if n)
        if skip and skip(name):
            continue
        referenced.add(name)
        if name in known or any(n in known for n in resolved):
            continue
        message = f"{label} not defined: {raw}"
        if resolved:
            message += (
                f" -> Note: {label} contains $PARAM but doesn't resolve to any defined {kind} "
                f"in any usage context. Check {kind} definitions and parameter names.")
        issues.append(create_issue(message, file=ref["file"], line=ref["line"],
                                   name=name, type=kind, severity="error"))

    for definition in definitions:
        name = definition["name"]
        if name in referenced or (skip and skip(name)):
            continue
        issues.append(create_issue(f"Unused {kind}: {name}", file=definition["file"],
                                   line=definition["line"], name=name, type=kind,
                                   severity="error"))
    return issues


def should_report_progress(count, total):
    """True when this count should be reported: the first ten, then every tenth or third."""
    if count <= 10:
        return True
    if total > 100:
        return count % 10 == 0
    return count % 3 == 0


def deduplicate_issues(issues):
    """Deduplicate issues on file, line and message, keeping the first of each."""
    seen = set()
    result = []
    for issue in issues:
        key = (issue['file'], issue['line'], issue['message'])
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


_FROM_INCLUDE = re.compile(r" \(from include '[^']*'\)$")
_EMPTY_ACTION = re.compile(r"Use 'noop' for an empty <(\w+)>$")


def merge_include_issues(issues):
    """Merge an include fault's per-call rows into one at its line, except a $PARAM a call fills."""
    sources = {}

    def source_line(path, line):
        if path not in sources:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    sources[path] = f.read().splitlines()
            except OSError:
                sources[path] = []
        text = sources[path]
        return text[line - 1] if 0 < line <= len(text) else ""

    merged = {}
    result = []
    for issue in issues:
        inc_file, inc_line = issue.get("include_file"), issue.get("include_line")
        message = _FROM_INCLUDE.sub("", issue["message"])
        param = _PARAM_PATTERN.search(source_line(inc_file, inc_line)) if inc_file and inc_line else None
        empty_action = _EMPTY_ACTION.match(message)
        # a $PARAM value is written at the call site, the line to fix, unless no call passes one
        if not (inc_file and inc_line) or (param and not empty_action):
            result.append(issue)
            continue
        if param and empty_action:
            message = (f"<{empty_action.group(1)}> is empty where a call passes no {param.group(1)}; "
                       f"give the {param.group(1)} param a default of noop")
        call = (issue.get("call_file") or issue.get("file"), issue.get("line"))
        group = merged.get((inc_file, inc_line, message))
        if group is None:
            group = {k: v for k, v in issue.items() if k not in ("include_file", "include_line")}
            group.update(file=inc_file, filename=os.path.basename(inc_file), line=inc_line,
                         message=message, call_file=call[0], call_line=call[1])
            merged[(inc_file, inc_line, message)] = (group, set())
            result.append(group)
        else:
            group = group[0]
        merged[(inc_file, inc_line, message)][1].add(call)
        if issue.get("severity") == "error":
            group["severity"] = "error"

    direct = {(i["file"], i["line"], i["message"]) for i in result if "call_line" not in i}
    dropped = set()
    for key, (group, calls) in merged.items():
        if key in direct:
            dropped.add(id(group))
            continue
        count = len(calls)
        group["message"] = (f"{group['message']} (include '{group['include_name']}', "
                            f"{count} call{'' if count == 1 else 's'})")
    return [issue for issue in result if id(issue) not in dropped]



def resolve_include_content(inc, resolve_callback=None):
    """Resolve the include body with its own default params substituted."""
    if resolve_callback:
        return resolve_callback(inc)

    content = inc.get("content") or ""
    if not content:
        return ""

    params = getattr(inc, "params", None) or {}
    try:
        resolved_text, _ = resolve_params_in_text(content, params, escape=True)
        return resolved_text
    except Exception:
        logger.debug("Failed to resolve params for include %s", getattr(inc, "name", "<unknown>"))
        return content


@lru_cache(maxsize=128)
def _get_font_name_pattern(font_name):
    """Cached regex matching a <name> element holding that font name."""
    return re.compile(r"<name>\s*%s\s*</name>" % re.escape(font_name), re.I)


def find_font_line_in_include(inc, font_name):
    """Line of the <font> block defining that font, or the include's own line if not found."""
    path = (inc.get("file") or "").strip()
    if not path or not os.path.isfile(path):
        return int(inc.get("line") or 1)

    try:
        with open(path, encoding="utf8", errors="ignore") as f:
            lines = list(f)

        start = max(int(inc.get("line") or 1) - 1, 0)
        pat = _get_font_name_pattern(font_name)

        for i in range(start, len(lines)):
            if pat.search(lines[i]):
                j = i
                while j >= 0 and "<font" not in lines[j].lower():
                    j -= 1
                return (j if j >= 0 else i) + 1
    except Exception:
        pass

    return int(inc.get("line") or 1)


def is_runtime_placeholder(text):
    """True when the text holds a placeholder only the running addon can fill in."""
    upper = text.upper()
    return "$SKINSHORTCUTS" in upper or "$PROPERTY[" in upper


def find_skinshortcuts_template(addon_path):
    """Path of the shortcuts template, newer name first, or None when the skin ships neither."""
    shortcuts_dir = os.path.join(addon_path, "shortcuts")
    for filename in ("templates.xml", "template.xml"):
        path = os.path.join(shortcuts_dir, filename)
        if os.path.isfile(path):
            return path
    return None


def skinshortcuts_files(addon_path):
    """Every xml file in the shortcuts folder, all of which feed the generated includes."""
    folder = os.path.join(addon_path, "shortcuts")
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [os.path.join(folder, name) for name in names if name.lower().endswith(".xml")]


def find_includes_in_skinshortcuts_template(template_path, known_include_names):
    """Known include names the shortcuts template refers to, in text or in an attribute."""
    from .xml import get_root_from_file

    if not os.path.isfile(template_path):
        return set()

    root = get_root_from_file(template_path)
    if root is None:
        return set()

    referenced = set()

    try:
        for text in root.xpath(".//text()"):
            text_stripped = text.strip()
            if not text_stripped or is_runtime_placeholder(text_stripped):
                continue
            for include_name in known_include_names:
                if include_name in text_stripped:
                    referenced.add(include_name)

        for attr in ("content", "include"):
            for elem in root.xpath(f".//*[@{attr}]"):
                value = elem.get(attr, "")
                if not value or is_runtime_placeholder(value):
                    continue
                if value in known_include_names:
                    referenced.add(value)

    except Exception:
        logger.exception("Error parsing SkinShortcuts template at %s", template_path)

    return referenced


def find_variables_in_skinshortcuts_file(template_path, known_variable_names):
    """Known variable names a shortcuts file refers to, in text or in an attribute."""
    from .xml import get_root_from_file

    if not os.path.isfile(template_path):
        return set()

    root = get_root_from_file(template_path)
    if root is None:
        return set()

    referenced = set()
    var_pattern = re.compile(r"\$(?:ESC)?VAR\[(.*?)\]", re.IGNORECASE)

    def _scan(text):
        for match in var_pattern.finditer(text):
            var_name = match.group(1).split(",")[0]
            if is_runtime_placeholder(var_name):
                continue
            if var_name in known_variable_names:
                referenced.add(var_name)

    try:
        for text in root.xpath(".//text()"):
            text_stripped = text.strip()
            if text_stripped:
                _scan(text_stripped)

        for elem in root.iter():
            for value in elem.attrib.values():
                if "$VAR[" in value.upper() or "$ESCVAR[" in value.upper():
                    _scan(value)

    except Exception:
        logger.exception("Error parsing SkinShortcuts template for variables at %s", template_path)

    return referenced


def find_variable_definitions_in_skinshortcuts_template(template_path):
    """Variable names the shortcuts template declares, which count as defined for the skin."""
    from .xml import get_root_from_file

    if not os.path.isfile(template_path):
        return set()

    root = get_root_from_file(template_path)
    if root is None:
        return set()

    defined = set()
    try:
        for var_elem in root.iter("variable"):
            name = var_elem.get("name", "").strip()
            if name and not is_runtime_placeholder(name):
                defined.add(name)
    except Exception:
        logger.exception("Error scanning variable definitions in %s", template_path)

    return defined
