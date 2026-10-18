"""Checks `<map>` definitions and `$MAP[]` usage against what Kodi loads."""

from __future__ import annotations

import os
import re
import logging
from ..utils.validation import (
    create_issue,
    get_all_parameter_contexts,
    resolve_param_in_name,
    skinshortcuts_files,
    should_report_progress,
)
from ..utils.xml import blank_xml_comments
from .constants import SEVERITY_ERROR

logger = logging.getLogger(__name__)

# skin maps start with Kodi 22; older releases print $MAP[] as plain text
MAPS_SINCE_RELEASE = "piers"

# Kodi matches the format prefixes case-sensitively
MAP_REF_REGEX = re.compile(r"\$(?:ESC)?MAP\[")


def extract_map_args(match_text):
    """Extract the leading `$MAP[...]` args; None when unclosed."""
    start = match_text.find('[')
    if start == -1:
        return None

    depth = 0
    for i, char in enumerate(match_text[start:], start=start):
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
            if depth == 0:
                body = match_text[start + 1:i]
                return body.split(",") if body else []
    return None


class ValidationMap:
    """Checker for `<map>` definitions and `$MAP[]` usage."""

    def __init__(self, addon):
        self.addon = addon
        self._resolution_cache = {}

    def check(self, progress_callback=None):
        """Check skin maps, one issue row per malformed, undefined or unused map."""
        issues = []
        supported = self._release_supports_maps()

        for folder in self.addon.xml_folders:
            definitions = self._collect_definitions(folder)
            usages = self._collect_usages(folder, progress_callback)

            winners = {d["name"]: d for d in definitions if d["name"]}

            if not supported:
                anchor = next(iter(definitions + usages), None)
                if anchor:
                    issues.append(self._issue(
                        "maps.unsupported",
                        anchor["file"], anchor["line"],
                        f"Skin maps need Kodi 22 (Piers); this skin targets "
                        f"{getattr(self.addon, 'api_version', '?')}",
                    ))

            issues.extend(self._check_definitions(definitions, winners))
            issues.extend(self._check_usages(folder, winners, usages))

        if progress_callback:
            progress_callback(f"Complete: {len(issues)} issues")

        return issues

    def _release_supports_maps(self):
        """True when the skin targets a Kodi release that has skin maps."""
        from ..addon.addon import Addon

        names = [item["name"] for item in Addon.RELEASES]
        target = getattr(self.addon, "api_version", None)
        if target not in names or MAPS_SINCE_RELEASE not in names:
            return True
        return names.index(target) >= names.index(MAPS_SINCE_RELEASE)

    def _collect_definitions(self, folder):
        """Collect every `<map>` in load order, with its ref and where it was written."""
        definitions = []
        for node, file_path in getattr(self.addon, "map_defs", {}).get(folder, []):
            definitions.append({
                # Kodi stores name and ref verbatim, whitespace included
                "name": node.attrib.get("name") or "",
                "ref": node.attrib.get("ref") or "",
                "node": node,
                "file": file_path,
                "line": getattr(node, "sourceline", 0) or 0,
            })
        return definitions

    def _collect_usages(self, folder, progress_callback=None):
        """Collect every `$MAP[]` / `$ESCMAP[]` reference in the folder and the shortcuts files."""
        paths = [
            os.path.join(self.addon.path, folder, xml_file)
            for xml_file in self.addon.window_files.get(folder, [])
        ]
        paths.extend(skinshortcuts_files(self.addon.path))

        usages = []
        for count, path in enumerate(paths, 1):
            if progress_callback and should_report_progress(count, len(paths)):
                progress_callback(f"Scanning {os.path.basename(path)} ({count}/{len(paths)})...")
            try:
                with open(path, encoding="utf8", errors="ignore") as f:
                    content = f.read()
            except OSError as e:
                logger.debug("Could not scan %s for skin maps: %s", path, e)
                continue

            if "$MAP[" not in content and "$ESCMAP[" not in content:
                continue

            content = blank_xml_comments(content)
            for match in MAP_REF_REGEX.finditer(content):
                usages.append({
                    "file": path,
                    "line": content.count("\n", 0, match.start()) + 1,
                    "args": extract_map_args(content[match.start():]),
                })
        return usages

    def _check_definitions(self, definitions, winners):
        """Check for names Kodi drops, entries it skips, and refs that go nowhere."""
        issues = []
        seen = {}

        for definition in definitions:
            name = definition["name"]
            if not name:
                issues.append(self._issue(
                    "maps.no-name",
                    definition["file"], definition["line"],
                    "<map> has no name attribute, so Kodi ignores it",
                ))
                continue

            if name != name.strip():
                issues.append(self._issue(
                    "maps.whitespace",
                    definition["file"], definition["line"],
                    f"Map name is padded with whitespace: '{name}'. $MAP[] trims the "
                    "name it looks up, so nothing can reach this map",
                    name=name,
                ))

            previous = seen.get(name)
            if previous:
                issues.append(self._issue(
                    "maps.duplicate",
                    definition["file"], definition["line"],
                    f"Duplicate map name: {name}. This replaces the definition in "
                    f"{os.path.basename(previous['file'])}:{previous['line']}",
                    name=name,
                ))
            seen[name] = definition

            issues.extend(self._check_entries(definition))

        issues.extend(self._check_refs(winners))
        return issues

    def _check_entries(self, definition):
        """Check for `<entry>` children Kodi refuses to load."""
        issues = []
        name = definition["name"]
        keys = set()

        for entry in definition["node"].findall("entry"):
            line = getattr(entry, "sourceline", 0) or 0
            key = entry.attrib.get("key")
            if not key:
                issues.append(self._issue(
                    "maps.no-key",
                    definition["file"], line,
                    f"<entry> in map '{name}' has no key attribute, so Kodi ignores it",
                    name=name,
                ))
                continue
            if entry.text is None:
                issues.append(self._issue(
                    "maps.no-value",
                    definition["file"], line,
                    f"Entry '{key}' in map '{name}' has no value, so Kodi ignores it",
                    name=name, subject=key,
                ))
                continue
            if key in keys:
                issues.append(self._issue(
                    "maps.duplicate-key",
                    definition["file"], line,
                    f"Duplicate entry key '{key}' in map '{name}'; the first value wins",
                    name=name, subject=key,
                ))
            keys.add(key)

        if not keys and not definition["ref"]:
            issues.append(self._issue(
                "maps.no-entries",
                definition["file"], definition["line"],
                f"Map '{name}' has no usable entries and no ref, so Kodi skips it",
                name=name,
            ))

        return issues

    def _check_refs(self, winners):
        """Check for unknown ref targets and ref chains that loop back on themselves."""
        issues = []
        reported_cycles = set()

        for name, definition in winners.items():
            ref = definition["ref"]
            if not ref:
                continue

            if ref != ref.strip():
                issues.append(self._issue(
                    "maps.ref-whitespace",
                    definition["file"], definition["line"],
                    f"Map '{name}' has a ref padded with whitespace: '{ref}'",
                    name=name,
                ))
                continue

            if ref not in winners:
                issues.append(self._issue(
                    "maps.undefined-ref",
                    definition["file"], definition["line"],
                    f"Map '{name}' references a map that is not defined: {ref}",
                    name=name,
                ))
                continue

            cycle = self._ref_cycle(name, winners)
            if cycle and frozenset(cycle) not in reported_cycles:
                reported_cycles.add(frozenset(cycle))
                issues.append(self._issue(
                    "maps.circular-ref",
                    winners[cycle[0]]["file"], winners[cycle[0]]["line"],
                    f"Circular map reference: {' -> '.join(cycle + [cycle[0]])}. "
                    "Kodi aborts the lookup and shows the raw value",
                    name=name,
                ))

        return issues

    @staticmethod
    def _ref_cycle(name, winners):
        """Names forming the loop the map leads into, or None when the chain ends."""
        chain = [name]
        current = name
        while True:
            ref = winners[current]["ref"]
            if ref not in winners:
                return None
            if ref in chain:
                return chain[chain.index(ref):]
            chain.append(ref)
            current = ref

    def _check_usages(self, folder, winners, usages):
        """Check for broken `$MAP[]` syntax, unknown map names, and definitions nothing reaches."""
        issues = []
        referenced = set()

        for usage in usages:
            args = usage["args"]
            if args is None:
                issues.append(self._issue(
                    "maps.bad-brackets",
                    usage["file"], usage["line"],
                    "$MAP[ is missing its closing ']'; Kodi discards the rest of the label",
                ))
                continue

            if len(args) < 2 or not args[0].strip() or not args[1].strip():
                issues.append(self._issue(
                    "maps.bad-syntax",
                    usage["file"], usage["line"],
                    "$MAP[] needs both a map name and an infolabel",
                ))
                continue

            raw_name = args[0].strip()
            names = {resolve_param_in_name(raw_name, None, self._resolution_cache)}
            if "$PARAM[" in raw_name:
                for context in get_all_parameter_contexts(self.addon, folder):
                    names.add(resolve_param_in_name(raw_name, context, self._resolution_cache))

            referenced.update(names)

            if any("$" in n for n in names):
                continue  # built at runtime, nothing to match against

            if not names & set(winners):
                issues.append(self._issue(
                    "maps.undefined",
                    usage["file"], usage["line"],
                    f"Map not defined: {raw_name}",
                    name=raw_name,
                ))

        issues.extend(self._check_unused(winners, referenced))
        return issues

    def _check_unused(self, winners, referenced):
        """Check for maps no `$MAP[]` reaches, directly or through another map's ref."""
        reachable = set()
        pending = [name for name in referenced if name in winners]
        while pending:
            name = pending.pop()
            if name in reachable:
                continue
            reachable.add(name)
            ref = winners[name]["ref"]
            if ref in winners:
                pending.append(ref)

        issues = []
        for name, definition in winners.items():
            if name in reachable:
                continue
            issues.append(self._issue(
                "maps.unused",
                definition["file"], definition["line"],
                f"Unused map: {name}",
                name=name,
            ))
        return issues

    @staticmethod
    def _issue(rule, file_path, line, message, name="", subject=None):
        """One map error row in the shape the report and quick panel expect, about the map named."""
        return create_issue(message, file_path, line, name=name, type="map", severity=SEVERITY_ERROR,
                            rule=rule, subject=name if subject is None else subject)
