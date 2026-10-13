"""Cached XML parsing, with a tag-balance pass that locates the real error line."""

import os
import re
import time
import logging
from lxml import etree as ET
from lxml.etree import XMLSyntaxError

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True

PARSER = ET.XMLParser(remove_blank_text=True, remove_comments=True, resolve_entities=False,
                      no_network=True, load_dtd=False)
FILE_PREVIEW_SIZE = 50_000

last_xml_errors = []
tolerated_xml_errors = {}
_xml_parse_cache = {}

_ENTITY = re.compile(r"&(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

_PARSE_MESSAGES = (
    (re.compile(r"(?:EntityRef: expecting ';'|xmlParseEntityRef: no name)$"),
     "Unescaped '&', write '&amp;'; Kodi drops a bare '&'"),
    (re.compile(r"Entity '([^']*)' not defined$"),
     "Unknown entity '&{0};', Kodi drops the '&'; write '&amp;' for a literal '&'"),
    (re.compile(r"StartTag: invalid element name$"),
     "Unescaped '<', write '&lt;'; Kodi cannot load the file"),
    (re.compile(r"error parsing attribute name$"),
     "Broken tag or unescaped '<'; write '&lt;' for a literal '<'"),
    (re.compile(r"Unescaped '<' not allowed in attributes values$"),
     "Unescaped '<' in an attribute, write '&lt;'"),
    (re.compile(r"attributes construct error$"),
     "Broken attribute, a quote inside the value ends it early; write '&quot;' or '&apos;'"),
    (re.compile(r"Sequence ']]>' not allowed in content$"),
     "Unescaped ']]>' in text, write ']]&gt;'"),
    (re.compile(r"XML declaration allowed only at the start of the document$"),
     "Text before <?xml, the declaration has to open the file"),
    (re.compile(r"Double hyphen within comment"),
     "'--' inside a comment, XML does not allow it"),
)


def _parse_xml_file(xml_file):
    """Parse a file into its root, as TinyXML reads it when only Kodi-tolerated faults break it."""
    try:
        root = ET.parse(xml_file, PARSER).getroot()
        tolerated_xml_errors.pop(xml_file, None)
        return root
    except XMLSyntaxError as e:
        error = _syntax_error(xml_file, e)
    except Exception:
        logger.exception("Unexpected error parsing %s", xml_file)
        return None

    root = _parse_as_tinyxml(xml_file)
    if root is not None:
        tolerated_xml_errors[xml_file] = error
        return root
    logger.error("Parse error in %s (line %d): %s", os.path.basename(xml_file), error["line"],
                 error["message"])
    last_xml_errors[:] = [error]
    return None


def _syntax_error(xml_file, e):
    """The parse error as {message, line, file}, in plain words and at the line to fix."""
    line = getattr(e, "position", (0, 0))[0]
    message = re.sub(r"\sline\s\d+(?:,\scolumn\s\d+)?", "", e.msg, flags=re.IGNORECASE).strip()
    message = message.rstrip(" ,")
    for pattern, plain in _PARSE_MESSAGES:
        found = pattern.match(message)
        if found:
            return {"message": plain.format(*found.groups()), "line": line, "file": xml_file}
    better = _check_tag_balance(xml_file)
    if better:
        return {"message": better["message"], "line": better["line"], "file": xml_file}
    return {"message": message, "line": line, "file": xml_file}


def _parse_as_tinyxml(xml_file):
    """Root of the file rewritten as TinyXML reads it, None when Kodi cannot load it either."""
    try:
        with open(xml_file, "rb") as f:
            text = f.read().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    rewritten = _as_tinyxml(text)
    if rewritten == text:
        return None
    try:
        return ET.fromstring(rewritten.encode("utf-8"), PARSER)
    except XMLSyntaxError:
        return None


def _as_tinyxml(text):
    """Rewrite the text as TinyXML reads it: stray '&' dropped, '<' and ']]>' escaped."""
    out = []
    lead = re.match(r"\s+(?=<\?xml)", text)
    i = lead.end() if lead else 0
    if lead:
        out.append("\n" * lead.group().count("\n"))
    n = len(text)
    while i < n:
        if text.startswith("<!--", i):
            end = text.find("-->", i + 4)
            if end == -1:
                out.append(text[i:])
                break
            out.append("<!--" + "\n" * text.count("\n", i, end) + "-->")
            i = end + 3
        elif text.startswith("<![CDATA[", i) or text.startswith("<?", i) or text.startswith("<!", i):
            closer = "]]>" if text.startswith("<![CDATA[", i) else ">"
            end = text.find(closer, i + 2)
            if end == -1:
                out.append(text[i:])
                break
            out.append(text[i:end + len(closer)])
            i = end + len(closer)
        elif text[i] == "<":
            i = _copy_tag(text, i, out)
        elif text[i] == "&" and not _ENTITY.match(text, i):
            i += 1
        elif text.startswith("]]>", i):
            out.append("]]&gt;")
            i += 3
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _copy_tag(text, i, out):
    """Copy the tag at the index into the output with its values fixed; index after the tag."""
    quote = None
    j = i
    while j < len(text):
        ch = text[j]
        if quote:
            if ch == quote:
                quote = None
                out.append(ch)
            elif ch == "<":
                out.append("&lt;")
            elif ch != "&" or _ENTITY.match(text, j):
                out.append(ch)
        else:
            out.append(ch)
            if ch in "\"'":
                quote = ch
            elif ch == ">" and j > i:
                return j + 1
        j += 1
    return j


def parse_error_issue(xml_file):
    """Error row for a file that failed to parse or loaded only as TinyXML reads it."""
    err = tolerated_xml_errors.get(xml_file) or next(
        (e for e in last_xml_errors if e["file"] == xml_file), None)
    return {
        "message": f"XML parse error: {err['message'] if err else 'file could not be parsed'}",
        "line": err["line"] if err else 1,
        "file": xml_file,
        "severity": "error",
        "type": "XML",
    }


def _extract_type_attr(text, attr_start, attr_end):
    """The type attribute inside the tag span, empty when it has none."""
    idx = text.find('type=', attr_start, attr_end)
    if idx == -1:
        return ""
    q = idx + 5
    if q < attr_end and text[q] in ('"', "'"):
        quote = text[q]
        end = text.find(quote, q + 1, attr_end)
        if end != -1:
            return text[q + 1:end]
    return ""


def _check_tag_balance(xml_file):
    """Find the opening tag that is never closed as {message, line}, None when they all match."""
    try:
        with open(xml_file, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception:
        return None

    stack = []
    i = 0
    line = 1

    while i < len(text):
        if text[i] == '\n':
            line += 1
            i += 1
            continue

        if text[i] != '<':
            i += 1
            continue

        if text[i:i+4] == '<!--':
            end = text.find('-->', i + 4)
            if end == -1:
                return {"message": "Unterminated comment", "line": line}
            line += text[i:end+3].count('\n')
            i = end + 3
            continue

        if text[i:i+9] == '<![CDATA[':
            end = text.find(']]>', i + 9)
            if end == -1:
                return {"message": "Unterminated CDATA section", "line": line}
            line += text[i:end+3].count('\n')
            i = end + 3
            continue

        if text[i:i+2] == '<?':
            end = text.find('?>', i + 2)
            if end == -1:
                return {"message": "Unterminated processing instruction", "line": line}
            line += text[i:end+2].count('\n')
            i = end + 2
            continue

        tag_start_line = line

        if text[i:i+2] == '</':
            end = text.find('>', i + 2)
            if end == -1:
                return {"message": "Unterminated closing tag", "line": line}
            line += text[i:end+1].count('\n')
            tag_name = text[i+2:end].strip()
            i = end + 1

            if not stack:
                return {"message": f"Unexpected closing tag </{tag_name}>", "line": tag_start_line}
            open_name, open_line, _ = stack[-1]
            if tag_name != open_name:
                return {
                    "message": f"Unclosed <{open_name}> (expected </{open_name}>, got </{tag_name}>)",
                    "line": open_line,
                }
            stack.pop()
            continue

        j = i + 1
        while j < len(text) and text[j] not in (' ', '\t', '\n', '\r', '>', '/'):
            j += 1
        tag_name = text[i+1:j]

        if not tag_name or not tag_name[0].isalpha():
            i = j
            continue

        # attribute values may hold > or a newline
        k = j
        while k < len(text):
            if text[k] == '"':
                k += 1
                while k < len(text) and text[k] != '"':
                    if text[k] == '\n':
                        line += 1
                    k += 1
            elif text[k] == "'":
                k += 1
                while k < len(text) and text[k] != "'":
                    if text[k] == '\n':
                        line += 1
                    k += 1
            elif text[k] == '>':
                break
            elif text[k] == '\n':
                line += 1
            k += 1

        if k >= len(text):
            return {"message": f"Unterminated tag <{tag_name}>", "line": tag_start_line}

        self_closing = k > 0 and text[k-1] == '/'
        i = k + 1

        if not self_closing:
            type_attr = ""
            if tag_name == "control":
                type_attr = _extract_type_attr(text, j, k)
                if stack and stack[-1][0] == "control" and stack[-1][2]:
                    top_type = stack[-1][2]
                    # only a group or grouplist nests controls
                    if top_type not in ("group", "grouplist"):
                        return {
                            "message": f"Unclosed <control type=\"{top_type}\">",
                            "line": stack[-1][1],
                        }
            stack.append((tag_name, tag_start_line, type_attr))

    if stack:
        open_name, open_line, _ = stack[-1]
        return {"message": f"Unclosed <{open_name}> at end of file", "line": open_line}

    return None


def get_root_from_file(xml_file):
    """Get a file's root node, cached on mtime and size; None when it cannot be parsed."""
    if not os.path.isfile(xml_file):
        # callers pass XML strings by mistake, so do not log the whole value
        preview = repr(xml_file)[:80]
        logger.debug("get_root_from_file: not a file path: %s...", preview)
        return None

    try:
        stat_info = os.stat(xml_file)
        mtime = stat_info.st_mtime
        size = stat_info.st_size
    except OSError:
        mtime = 0
        size = 0

    cached_mtime, cached_size, cached_root = _xml_parse_cache.get(xml_file, (None, None, None))
    if cached_mtime == mtime and cached_size == size and cached_root is not None:
        return cached_root

    start_time = time.time()

    root = _parse_xml_file(xml_file)

    parse_duration = time.time() - start_time
    if root is not None:
        _xml_parse_cache[xml_file] = (mtime, size, root)
        if parse_duration > 0.1:
            logger.debug("get_root_from_file SUCCESS: file=%s duration=%.3fs", os.path.basename(xml_file), parse_duration)
    else:
        logger.warning("get_root_from_file FAILED: file=%s duration=%.3fs", os.path.basename(xml_file), parse_duration)

    return root


def blank_xml_comments(content):
    """Blank out `<!-- ... -->`, keeping every newline."""
    return _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), content)


def check_brackets(label):
    """True when every round and square bracket in the text is closed by its own kind, in order."""
    stack = []
    push_chars, pop_chars = "([", ")]"
    for c in label:
        if c in push_chars:
            stack.append(c)
        elif c in pop_chars:
            if not stack:
                return False
            else:
                stack_top = stack.pop()
                balancing_bracket = push_chars[pop_chars.index(c)]
                if stack_top != balancing_bracket:
                    return False
    return not stack


def param_value(param, value_attr):
    """Value of one <param>, the attribute before the text (see GUIIncludes.cpp:583)."""
    value = param.get(value_attr)
    if value is None:
        value = (param.text or "").strip()
    return value


def get_params(include, value_attr):
    """Get an include's named <param> values, keeping the first of each name as Kodi does."""
    params = {}
    for param in include.findall("param"):
        name = param.get("name")
        if name and name not in params:
            params[name] = param_value(param, value_attr)
    return params


def file_needs_expansion(path, max_bytes=FILE_PREVIEW_SIZE):
    """True when the file's first bytes hold an include or a $PARAM, so it may need resolving."""
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(max_bytes)
            return '$PARAM[' in content or '<include' in content
    except Exception:
        # unreadable, so assume it needs the pass
        return True


def tree_needs_expansion(root):
    """True when a parsed tree holds an include or a dynamic value, so it may need resolving."""
    if root is None:
        return False

    if root.find('.//include') is not None:
        return True

    dynamic_patterns = ('$param', '$var', '$constant', '$exp')

    for elem in root.iter():
        if elem.text:
            text_lower = elem.text.casefold()
            if any(pattern in text_lower for pattern in dynamic_patterns):
                return True

        for attr_value in elem.attrib.values():
            if attr_value:
                value_lower = attr_value.casefold()
                if any(pattern in value_lower for pattern in dynamic_patterns):
                    return True

    return False
