"""
XML parsing and validation utilities for KodiDevKit.
"""

import os
import re
import logging
from lxml import etree as ET
from lxml.etree import XMLSyntaxError

logger = logging.getLogger("KodiDevKit.utils.xml")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True

PARSER = ET.XMLParser(remove_blank_text=True, remove_comments=True)
FILE_PREVIEW_SIZE = 50_000

last_xml_errors = []
_xml_parse_cache = {}


def _parse_xml_file(xml_file):
    """Parse XML file and return root. Raises exceptions on error."""
    try:
        return ET.parse(xml_file, PARSER).getroot()
    except XMLSyntaxError as e:
        lxml_line = getattr(e, "position", (0, 0))[0]
        msg = re.sub(r"\sline\s\d+(?:,\scolumn\s\d+)?", "", e.msg, flags=re.IGNORECASE).strip()
        short_msg = msg.rstrip(" ,")

        # Try tag-balance checker for a better error location
        better = _check_tag_balance(xml_file)
        if better:
            logger.error("Parse error in %s (line %d): %s", os.path.basename(xml_file), better["line"], better["message"])
            last_xml_errors[:] = [{"message": better["message"], "line": better["line"], "file": xml_file}]
        else:
            logger.error("Parse error in %s (line %d): %s", os.path.basename(xml_file), lxml_line, short_msg)
            last_xml_errors[:] = [{"message": short_msg, "line": lxml_line, "file": xml_file}]
        return None
    except Exception:
        logger.exception("Unexpected error parsing %s", xml_file)
        return None


def _extract_type_attr(text, attr_start, attr_end):
    """Extract type attribute value from tag content between attr_start..attr_end."""
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
    """Stack-based tag balance checker that pinpoints the actual error location.

    Unlike lxml which reports where it detected the problem (usually a closing
    tag far from the mistake), this walks the file tracking open/close tags and
    reports the opening tag that has no matching close.

    For <control> siblings with the same type attribute (e.g. multiple
    grouplist controls), detects the unclosed tag immediately when the next
    sibling of the same type opens — only group type can self-nest.

    Returns dict with message/line on error, or None if no mismatch found.
    """
    try:
        with open(xml_file, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception:
        return None

    stack = []  # (tag_name, line_number, type_attr)
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

        # Skip comments <!-- ... -->
        if text[i:i+4] == '<!--':
            end = text.find('-->', i + 4)
            if end == -1:
                return {"message": "Unterminated comment", "line": line}
            line += text[i:end+3].count('\n')
            i = end + 3
            continue

        # Skip CDATA <![CDATA[ ... ]]>
        if text[i:i+9] == '<![CDATA[':
            end = text.find(']]>', i + 9)
            if end == -1:
                return {"message": "Unterminated CDATA section", "line": line}
            line += text[i:end+3].count('\n')
            i = end + 3
            continue

        # Skip processing instructions <? ... ?>
        if text[i:i+2] == '<?':
            end = text.find('?>', i + 2)
            if end == -1:
                return {"message": "Unterminated processing instruction", "line": line}
            line += text[i:end+2].count('\n')
            i = end + 2
            continue

        tag_start_line = line

        # Closing tag </name>
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

        # Opening or self-closing tag
        # Extract tag name
        j = i + 1
        while j < len(text) and text[j] not in (' ', '\t', '\n', '\r', '>', '/'):
            j += 1
        tag_name = text[i+1:j]

        if not tag_name or not tag_name[0].isalpha():
            i = j
            continue

        # Scan to end of tag, respecting quoted attributes
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

        # Self-closing if ends with />
        self_closing = k > 0 and text[k-1] == '/'
        i = k + 1

        if not self_closing:
            type_attr = ""
            if tag_name == "control":
                type_attr = _extract_type_attr(text, j, k)
                if stack and stack[-1][0] == "control" and stack[-1][2]:
                    top_type = stack[-1][2]
                    # Only group/grouplist can contain child controls
                    if top_type not in ("group", "grouplist"):
                        return {
                            "message": f"Unclosed <control type=\"{top_type}\">",
                            "line": stack[-1][1],
                        }
                    # Same non-group type can't self-nest (sibling detection)
                    if (type_attr and top_type == type_attr
                            and type_attr != "group"):
                        return {
                            "message": f"Unclosed <control type=\"{type_attr}\">",
                            "line": stack[-1][1],
                        }
            stack.append((tag_name, tag_start_line, type_attr))

    if stack:
        open_name, open_line, _ = stack[-1]
        return {"message": f"Unclosed <{open_name}> at end of file", "line": open_line}

    return None


def get_root_from_file(xml_file):
    """Return XML root node from file with mtime+size-based caching.

    Cache is validated using both mtime and file size to prevent stale caches
    when files are modified rapidly (within filesystem mtime granularity).
    This adds zero overhead since os.stat() returns both values.
    """
    import time

    if not os.path.isfile(xml_file):
        # Truncate to avoid dumping entire XML strings into the log
        preview = repr(xml_file)[:80]
        logger.debug("get_root_from_file: not a file path: %s...", preview)
        return None
    if not os.path.exists(xml_file):
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
        # Only log slow parses (>100ms) to reduce noise
        if parse_duration > 0.1:
            logger.debug("get_root_from_file SUCCESS: file=%s duration=%.3fs", os.path.basename(xml_file), parse_duration)
    else:
        logger.warning("get_root_from_file FAILED: file=%s duration=%.3fs", os.path.basename(xml_file), parse_duration)

    return root


def check_brackets(label):
    """
    check if all brackets in *label match, return True / False
    """
    stack = []
    push_chars, pop_chars = "<({[", ">)}]"
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


def file_needs_expansion(path, max_bytes=FILE_PREVIEW_SIZE):
    """
    Quick check if XML file likely needs include/param expansion.

    Reads first max_bytes of file and checks for $PARAM or <include patterns.
    Used to avoid expensive expansion on static files.

    Args:
        path: File path to check
        max_bytes: Maximum bytes to read for check (default 50KB)

    Returns:
        bool: True if file likely needs expansion
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(max_bytes)
            return '$PARAM[' in content or '<include' in content
    except Exception:
        # If we can't read the file, assume it needs expansion to be safe
        return True


def tree_needs_expansion(root):
    """
    Check if parsed XML tree needs expansion (no file I/O required).

    More efficient than file_needs_expansion() when tree is already parsed,
    avoiding redundant file reads.

    Args:
        root: Parsed XML ElementTree root element

    Returns:
        bool: True if tree likely needs expansion
    """
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
