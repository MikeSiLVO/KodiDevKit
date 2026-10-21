"""Plain-text validation report for the export endpoint, free of `sublime`."""

from typing import Container

from ..validation.constants import SEVERITY_ERROR, SEVERITY_WARNING
from ..validation.suppress import muted_note


def issue_visible(issue, hidden_severities, hide_include_warnings, hide_muted=False):
    """True when the issue passes the HTML report's severity, include-warning and muted filters."""
    severity = issue.get("severity", SEVERITY_WARNING)
    if severity in hidden_severities:
        return False
    if hide_muted and issue.get("muted"):
        return False
    if hide_include_warnings and issue.get("include_name") and severity != SEVERITY_ERROR:
        return False
    return True


def generate_text_report(report_data, *, hidden_severities: Container[str] = frozenset(),
                         hide_include_warnings=False, hide_muted=False):
    """Generate the text report, honoring the same filters as the HTML report."""
    lines = []
    lines.append("=" * 80)
    lines.append("KODI SKIN VALIDATION REPORT")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Skin: {report_data.get('skin_name', 'Unknown')}")
    lines.append(f"Path: {report_data.get('skin_path', 'Unknown')}")
    lines.append(f"Generated: {report_data.get('timestamp', 'Unknown')}")
    lines.append("")
    lines.append("=" * 80)
    lines.append("SUMMARY")
    lines.append("=" * 80)
    lines.append("")

    all_issues_raw = report_data.get('all_issues', {})

    all_issues = {}
    total_filtered_out = 0

    for category, issues in all_issues_raw.items():
        kept = []
        for issue in issues:
            if not issue_visible(issue, hidden_severities, hide_include_warnings, hide_muted):
                total_filtered_out += 1
                continue
            kept.append(issue)
        if kept:
            all_issues[category] = kept

    total_issues = sum(len(issues) for issues in all_issues.values())
    total_muted = sum(1 for issues in all_issues.values() for issue in issues if issue.get("muted"))
    lines.append(f"Total Issues: {total_issues - total_muted}")
    if total_muted:
        lines.append(f"Muted: {total_muted}")
    lines.append(f"Categories: {len([c for c, issues in all_issues.items() if issues])}")

    filter_notes = _describe_filters(hidden_severities, hide_include_warnings, hide_muted)
    if filter_notes:
        lines.append("")
        lines.append(f"Filters: {filter_notes} ({total_filtered_out} issue{'s' if total_filtered_out != 1 else ''} hidden)")

    lines.append("")

    lines.append("-" * 80)
    lines.append("ISSUES BY CATEGORY")
    lines.append("-" * 80)
    lines.append("")

    for category, issues in all_issues.items():
        if not issues:
            continue

        lines.append("")
        lines.append(f"{'#' * 60}")
        lines.append(f"# {category.upper()} ({len(issues)} issues)")
        lines.append(f"{'#' * 60}")
        lines.append("")

        by_file = {}
        for issue in issues:
            file_path = issue.get('file', 'Unknown')
            by_file.setdefault(file_path, []).append(issue)

        for file_path in sorted(by_file.keys()):
            file_issues = by_file[file_path]
            lines.append(f"  File: {file_path}{_muted_count(file_issues)}")
            lines.append(f"  {'-' * 76}")

            by_mute = {}
            for issue in file_issues:
                mute = issue.get("muted")
                if mute:
                    by_mute.setdefault((mute["line"], mute.get("reason") or ""), []).append(issue)
                else:
                    lines.extend(_row_lines(issue, "    "))
            for key in sorted(by_mute):
                lines.append(f"    {muted_note(by_mute[key][0])}")
                for issue in by_mute[key]:
                    lines.extend(_row_lines(issue, "      "))

    lines.append("")
    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)

    return '\n'.join(lines)


def _row_lines(issue, indent):
    """Lines for one issue: severity, line and message, then any type, then a blank."""
    label = issue.get("severity", SEVERITY_WARNING).upper()
    lines = [f"{indent}{label:<8s} line {issue.get('line', 0):<5d} {issue.get('message', 'No message')}"]
    if issue.get("type"):
        lines.append(f"{indent}{' ' * 20}Type: {issue['type']}")
    lines.append("")
    return lines


def _muted_count(issues):
    """Heading note counting a file's muted issues per severity; empty when none are muted."""
    muted = [issue.get("severity", SEVERITY_WARNING) for issue in issues if issue.get("muted")]
    parts = []
    for sev in (SEVERITY_ERROR, SEVERITY_WARNING):
        count = muted.count(sev)
        if count:
            parts.append(f"{count} muted {sev}{'s' if count != 1 else ''}")
    return f"  ({', '.join(parts)})" if parts else ""


def _describe_filters(hidden_severities, hide_include_warnings, hide_muted=False):
    """Describe the active filters, or return an empty string when none are active."""
    parts = []
    for sev in (SEVERITY_ERROR, SEVERITY_WARNING):
        if sev in hidden_severities:
            parts.append(f"{sev}s hidden")
    if hide_include_warnings:
        parts.append("include warnings hidden")
    if hide_muted:
        parts.append("muted issues hidden")
    return ", ".join(parts)
