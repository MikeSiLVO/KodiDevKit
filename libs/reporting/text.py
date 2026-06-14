"""Plain-text validation report, shared by the export endpoint.

Kept free of the `sublime` import so the formatting/filtering is unit-testable.
"""

from typing import Container

from .. import utils
from ..validation.constants import SEVERITY_ERROR, SEVERITY_WARNING


def issue_visible(issue, hidden_severities, hide_include_warnings):
    """Mirror the HTML report's filters: an issue is visible unless its severity
    is hidden, or it is an include-sourced warning while those are hidden.

    Include warnings are `include_name` set and severity != error -- matches
    kdk's filter_include_warnings and the on-page toggle.
    """
    severity = issue.get("severity", SEVERITY_WARNING)
    if severity in hidden_severities:
        return False
    if hide_include_warnings and issue.get("include_name") and severity != SEVERITY_ERROR:
        return False
    return True


def generate_text_report(report_data, *, hidden_severities: Container[str] = frozenset(), hide_include_warnings=False):
    """Render `report_data` to text, honoring the same filters as the HTML view."""
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

    # Drop runtime-generated files, then apply the on-page filters.
    all_issues = {}
    total_runtime_excluded = 0
    total_filtered_out = 0

    for category, issues in all_issues_raw.items():
        kept = []
        for issue in issues:
            if utils.is_runtime_generated_file(issue.get("file", "")):
                total_runtime_excluded += 1
                continue
            if not issue_visible(issue, hidden_severities, hide_include_warnings):
                total_filtered_out += 1
                continue
            kept.append(issue)
        if kept:
            all_issues[category] = kept

    total_issues = sum(len(issues) for issues in all_issues.values())
    lines.append(f"Total Issues: {total_issues}")
    lines.append(f"Categories: {len([c for c, issues in all_issues.items() if issues])}")

    filter_notes = _describe_filters(hidden_severities, hide_include_warnings)
    if filter_notes:
        lines.append("")
        lines.append(f"Filters: {filter_notes} ({total_filtered_out} issue{'s' if total_filtered_out != 1 else ''} hidden)")

    if total_runtime_excluded > 0:
        lines.append("")
        lines.append(f"Note: {total_runtime_excluded} runtime-generated issue{'s' if total_runtime_excluded != 1 else ''} from")
        lines.append("      script-skinvariables-*.xml files excluded from this report.")
        lines.append("      These files are auto-generated and over-generation is expected.")

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
            lines.append(f"  File: {file_path}")
            lines.append(f"  {'-' * 76}")

            for issue in file_issues:
                line_num = issue.get('line', 0)
                message = issue.get('message', 'No message')
                issue_type = issue.get('type', '')

                lines.append(f"    Line {line_num:4d}: {message}")
                if issue_type:
                    lines.append(f"                Type: {issue_type}")
                lines.append("")

    lines.append("")
    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)

    return '\n'.join(lines)


def _describe_filters(hidden_severities, hide_include_warnings):
    """Human-readable summary of active filters, or empty string if none."""
    parts = []
    for sev in (SEVERITY_ERROR, SEVERITY_WARNING):
        if sev in hidden_severities:
            parts.append(f"{sev}s hidden")
    if hide_include_warnings:
        parts.append("include warnings hidden")
    return ", ".join(parts)
