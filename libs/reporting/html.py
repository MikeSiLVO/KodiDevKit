"""
HTML report generator for KodiDevKit validation results.
"""

import os
import html
from datetime import datetime
from collections import defaultdict
from .. import utils
from ..validation.constants import SEVERITY_ERROR, SEVERITY_WARNING

CATEGORY_DESCRIPTIONS = {
    "Variables": (
        "<strong>Errors:</strong> Variable referenced but not defined, or defined but never used. "
        "Both block Kodi repo submission."
    ),
    "Includes": (
        "<strong>Errors:</strong> Include referenced but not defined, or defined but never used. "
        "Both block Kodi repo submission."
    ),
    "Labels": (
        "<strong>Errors:</strong> Numeric label ID not found in translation files &mdash; will show as empty text in Kodi. "
        "<strong>Warnings:</strong> Hardcoded text or possible missing $INFO[] wrapper. "
        "Kodi still renders these, but they cannot be translated."
    ),
    "Fonts": (
        "<strong>Errors:</strong> Missing font file, undefined font, missing required elements, no unicode fontset. "
        "<strong>Warnings:</strong> Case mismatches, unused definitions, cross-fontset inconsistencies. "
        "Kodi resolves font names case-insensitively so these still work, but indicate sloppy references."
    ),
    "IDs": (
        "<strong>Errors:</strong> Window or control ID referenced but not defined, or numeric window ID used where a name is required."
    ),
    "Images": (
        "<strong>Errors:</strong> Image file not found on disk &mdash; will render as blank in Kodi. "
        "<strong>Warnings:</strong> Case mismatches or wrong relative paths. "
        "Kodi resolves case-insensitively so these still display, but will break on case-sensitive filesystems (Linux)."
    ),
    "XML Validation": (
        "<strong>Errors:</strong> Invalid color values, invalid integers, unknown XML tags. "
        "<strong>Warnings:</strong> Invalid tags, repeated tags that should appear only once, invalid attributes. "
        "Kodi silently ignores these &mdash; flagged here to teach correct XML structure."
    ),
    "File Integrity": (
        "<strong>Errors:</strong> BOM detected, Windows or Mac line endings. All block Kodi repo submission."
    ),
}

# Ordered: first match wins
_SUBTYPE_RULES = [
    ("Missing image", "MISSING"),
    ("Case mismatch for", "CASE MISMATCH"),
    ("Wrong path", "WRONG PATH"),
    ("Case mismatch in font", "CASE MISMATCH"),
    ("not defined in Fonts.xml", "UNDEFINED"),
    ("Unused font", "UNUSED"),
    ("missing font '", "INCONSISTENT"),
    ("has extra font '", "INCONSISTENT"),
    ("Duplicate font name", "DUPLICATE"),
    ("no extension", "BAD FILENAME"),
    ("Non-TTF font", "BAD FILENAME"),
    ("font13", "MISSING FONT13"),
    ("missing required", "MISSING TAG"),
    ("no unicode", "NO UNICODE"),
    ("Missing font file", "MISSING FILE"),
    ("Label not defined", "UNDEFINED"),
    ("not translated", "NOT TRANSLATED"),
    ("missing $INFO[]", "MISSING INFO"),
    ("Possible addon ID", "ADDON ID"),
    ("Window ID not defined", "UNDEFINED"),
    ("Control ID", "UNDEFINED"),
    ("Please use", "USE NAME"),
    ("Unused variable", "UNUSED"),
    ("not defined", "UNDEFINED"),
    ("Unused include", "UNUSED"),
    ("is not a valid child", "INVALID TAG"),
    ("is not valid for", "INVALID TAG"),
    ("is not valid inside", "INVALID TAG"),
    ("invalid tag for", "INVALID TAG"),
    ("Invalid multiple tags", "DUPLICATE TAG"),
    ("invalid attribute for", "INVALID ATTR"),
    ("invalid value for", "INVALID VALUE"),
    ("Invalid color", "INVALID COLOR"),
    ("invalid integer", "INVALID VALUE"),
    ("Empty condition", "EMPTY CONDITION"),
    ("Brackets do not match", "BAD BRACKETS"),
    ("Use 'noop'", "HINT"),
    ("BOM", "BOM"),
    ("Windows Line Endings", "LINE ENDINGS"),
    ("MAC Line Endings", "LINE ENDINGS"),
]


def _classify_subtype(message: str) -> str:
    """Derive a short subtype tag from the issue message."""
    for pattern, label in _SUBTYPE_RULES:
        if pattern in message:
            return label
    return ""


def generate_html_report(all_issues, skin_name, skin_path, output_path=None, server_port=48273, progress_callback=None):
    """
    Generate a comprehensive HTML report of all validation issues.

    Args:
        all_issues: Dict with check names as keys and lists of issues as values
        skin_name: Name of the skin being checked
        skin_path: Path to the skin directory
        output_path: Optional path to save the report (default: skin_path/validation_report.html)
        server_port: Port number for the local HTTP server (default: 48273)
        progress_callback: Optional callback function(message: str) for progress updates

    Returns:
        Path to the generated HTML file
    """
    if output_path is None:
        output_path = os.path.join(skin_path, "validation_report.html")

    if progress_callback:
        progress_callback("Calculating statistics...")

    normal_issues = {}
    runtime_issues = {}

    for category, issues in all_issues.items():
        normal_list = []
        runtime_list = []

        for issue in issues:
            if utils.is_runtime_generated_file(issue.get("file", "")):
                runtime_list.append(issue)
            else:
                normal_list.append(issue)

        if normal_list:
            normal_issues[category] = normal_list
        if runtime_list:
            runtime_issues[category] = runtime_list

    total_normal_issues = sum(len(issues) for issues in normal_issues.values())
    total_runtime_issues = sum(len(issues) for issues in runtime_issues.values())

    normal_categories = {name: len(issues) for name, issues in normal_issues.items() if issues}

    if progress_callback:
        progress_callback(f"Grouping {total_normal_issues} actionable issues ({total_runtime_issues} runtime-generated excluded)...")

    issues_by_file = defaultdict(list)
    for category, issues in normal_issues.items():
        for issue in issues:
            file_path = issue.get("file", "Unknown")
            issues_by_file[file_path].append({**issue, "category": category})

    if progress_callback:
        progress_callback(f"Generating HTML report ({len(normal_categories)} categories, {len(issues_by_file)} files)...")

    html_content = _generate_html_template(
        skin_name, skin_path, total_normal_issues, total_runtime_issues,
        normal_categories, normal_issues, issues_by_file, server_port, progress_callback
    )

    if progress_callback:
        progress_callback("Writing report to disk...")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    if progress_callback:
        progress_callback("Report generation complete!")

    return output_path


def _generate_html_template(skin_name, skin_path, total_issues, total_runtime_excluded,
                            categories, all_issues, issues_by_file, server_port, progress_callback=None):
    """Generate the complete HTML report template."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_errors = 0
    total_warnings = 0
    for issues in all_issues.values():
        for issue in issues:
            sev = issue.get("severity", "warning")
            if sev == SEVERITY_ERROR:
                total_errors += 1
            elif sev == SEVERITY_WARNING:
                total_warnings += 1

    category_sections = []
    category_count = 0
    total_categories = len(categories)

    sorted_categories = sorted(
        [(cat, issues) for cat, issues in all_issues.items() if issues],
        key=lambda x: -len(x[1])
    )

    for category, issues in sorted_categories:
        category_count += 1
        if progress_callback and category_count % 2 == 0:  # Update every 2 categories
            progress_callback(f"Building category sections... ({category_count}/{total_categories})")
        section = _generate_category_section(category, issues, server_port)
        category_sections.append(section)

    file_sections = []
    file_count = 0
    total_files = len(issues_by_file)

    if progress_callback:
        progress_callback(f"Building file sections... (0/{total_files})")

    for file_path in sorted(issues_by_file.keys()):
        file_count += 1
        if progress_callback and (file_count % 3 == 0 or file_count == total_files):  # Update every 3 files for better feedback
            progress_callback(f"Building file sections... ({file_count}/{total_files})")
        section = _generate_file_section(file_path, issues_by_file[file_path], server_port)
        file_sections.append(section)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Validation Report - {html.escape(skin_name)}</title>
    <style>
        {_get_css_styles()}
    </style>
    <script>
        // Check if server is running when page loads
        fetch('http://localhost:{server_port}/ping')
            .then(response => {{
                if (response.ok) {{
                    document.getElementById('server-status').innerHTML =
                        '<span style="color: #4CAF50;">● Connected</span> - Click any file link to open in Sublime Text';
                }}
            }})
            .catch(() => {{
                document.getElementById('server-status').innerHTML =
                    '<span style="color: #ff9800;">⚠ Server not running</span> - Start Sublime Text to enable direct file opening';
            }});

        // Show notification toast when file link is clicked
        function showNotification(fileName, lineNumber) {{
            // Remove any existing notification
            const existing = document.getElementById('file-notification');
            if (existing) {{
                existing.remove();
            }}

            // Platform-specific hint message
            const platform = navigator.platform.toLowerCase();
            let hintMessage = 'Switch to Sublime Text to view the file';

            if (platform.includes('win')) {{
                hintMessage = 'Check your taskbar for the flashing Sublime Text icon';
            }} else if (platform.includes('mac')) {{
                hintMessage = 'Sublime Text should now be in focus';
            }} else if (platform.includes('linux')) {{
                hintMessage = 'Sublime Text window has been activated';
            }}

            // Create notification element
            const notification = document.createElement('div');
            notification.id = 'file-notification';
            notification.innerHTML = `
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="font-size: 28px;">📂</div>
                    <div style="flex: 1;">
                        <div style="font-weight: bold; margin-bottom: 4px;">File Opened in Sublime Text</div>
                        <div style="font-size: 0.9em; opacity: 0.9;">
                            ${{fileName}}:${{lineNumber}}
                        </div>
                        <div style="font-size: 0.85em; opacity: 0.7; margin-top: 4px;">
                            ${{hintMessage}}
                        </div>
                    </div>
                    <button onclick="this.parentElement.parentElement.remove()"
                            style="background: none; border: none; color: white; font-size: 20px; cursor: pointer; opacity: 0.7; padding: 0 8px;">
                        ✕
                    </button>
                </div>
            `;

            // Apply styles
            notification.style.cssText = `
                position: fixed;
                bottom: 40px;
                right: 40px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px 24px;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(102, 126, 234, 0.4);
                z-index: 10000;
                min-width: 400px;
                max-width: 500px;
                animation: slideInUp 0.3s ease-out;
                margin: 0;
            `;

            document.body.appendChild(notification);

            // Auto-remove after 5 seconds
            setTimeout(() => {{
                if (notification.parentElement) {{
                    notification.style.animation = 'slideOutDown 0.3s ease-in';
                    setTimeout(() => notification.remove(), 300);
                }}
            }}, 5000);
        }}

        // Add click handlers to all file links
        document.addEventListener('DOMContentLoaded', function() {{
            const fileLinks = document.querySelectorAll('a.file-link');
            fileLinks.forEach(link => {{
                link.addEventListener('click', function(e) {{
                    // Extract filename and line from the href or text
                    const fileName = this.textContent.trim();
                    const href = this.getAttribute('href');
                    const lineMatch = href.match(/line=(\\d+)/);
                    const lineNumber = lineMatch ? lineMatch[1] : '?';

                    showNotification(fileName, lineNumber);
                }});
            }});
        }});

        // Severity filtering — warnings hidden by default (educational, not actionable)
        const hiddenSeverities = new Set(['warning']);

        function toggleSeverity(severity, btn) {{
            if (hiddenSeverities.has(severity)) {{
                hiddenSeverities.delete(severity);
                btn.classList.add('active');
            }} else {{
                hiddenSeverities.add(severity);
                btn.classList.remove('active');
            }}
            applySeverityFilter();
        }}

        function applySeverityFilter() {{
            // Hide/show table rows and list items by severity class
            ['error', 'warning'].forEach(sev => {{
                const hidden = hiddenSeverities.has(sev);
                document.querySelectorAll('.severity-' + sev).forEach(el => {{
                    el.style.display = hidden ? 'none' : '';
                }});
            }});

            let totalErrors = 0;
            let totalWarnings = 0;

            // Update category section badges
            document.querySelectorAll('.category-section').forEach(section => {{
                const rows = section.querySelectorAll('tbody tr');
                const visible = Array.from(rows).filter(tr => tr.style.display !== 'none').length;
                const badge = section.querySelector('h3 .badge');
                if (badge) badge.textContent = visible;
                // Hide entire section if no visible issues
                section.style.display = visible === 0 ? 'none' : '';
                // Count errors/warnings
                totalErrors += Array.from(rows).filter(tr => tr.style.display !== 'none' && tr.classList.contains('severity-error')).length;
                totalWarnings += Array.from(rows).filter(tr => tr.style.display !== 'none' && tr.classList.contains('severity-warning')).length;
            }});

            // Update summary table counts per category (error/warning split)
            document.querySelectorAll('.summary-table tbody tr').forEach(row => {{
                const link = row.querySelector('a[href^="#cat-"]');
                if (!link) return;
                const catId = link.getAttribute('href').substring(1);
                const section = document.getElementById(catId);
                if (!section) return;
                const visibleRows = Array.from(section.querySelectorAll('tbody tr'))
                    .filter(tr => tr.style.display !== 'none');
                const errCount = visibleRows.filter(tr => tr.classList.contains('severity-error')).length;
                const warnCount = visibleRows.filter(tr => tr.classList.contains('severity-warning')).length;
                const errBadge = row.querySelector('.badge-error');
                const warnBadge = row.querySelector('.badge-warning');
                if (errBadge) errBadge.textContent = errCount;
                if (warnBadge) warnBadge.textContent = warnCount;
                row.style.display = (errCount + warnCount) === 0 ? 'none' : '';
            }});

            // Update file sections
            document.querySelectorAll('.file-section').forEach(section => {{
                const items = section.querySelectorAll('li');
                const visible = Array.from(items).filter(li => li.style.display !== 'none').length;
                const badge = section.querySelector('h3 .badge');
                if (badge) badge.textContent = visible;
                section.style.display = visible === 0 ? 'none' : '';
            }});

            // Update error/warning stat boxes
            const errorStat = document.querySelector('.stat-number-error');
            const warningStat = document.querySelector('.stat-number-warning');
            if (errorStat) errorStat.textContent = totalErrors;
            if (warningStat) warningStat.textContent = totalWarnings;
        }}

        // Apply default filter on load
        document.addEventListener('DOMContentLoaded', applySeverityFilter);
    </script>
    <style>
        @keyframes slideInUp {{
            from {{
                transform: translateY(100px);
                opacity: 0;
            }}
            to {{
                transform: translateY(0);
                opacity: 1;
            }}
        }}

        @keyframes slideOutDown {{
            from {{
                transform: translateY(0);
                opacity: 1;
            }}
            to {{
                transform: translateY(100px);
                opacity: 0;
            }}
        }}

        #file-notification button:hover {{
            opacity: 1 !important;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <h1>🔍 Kodi Skin Validation Report</h1>
                    <div class="meta">
                        <p><strong>Skin:</strong> {html.escape(skin_name)}</p>
                        <p><strong>Path:</strong> <code>{html.escape(skin_path)}</code></p>
                        <p><strong>Generated:</strong> {timestamp}</p>
                        <p id="server-status" style="margin-top: 10px; padding: 8px; background: rgba(255,255,255,0.1); border-radius: 4px;">
                            <span style="color: #ccc;">● Checking connection...</span>
                        </p>
                    </div>
                </div>
                <div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px; align-items: flex-end;">
                    <a href="http://localhost:{server_port}/export" class="export-button" download="validation_report.txt">
                        📥 Export to Text
                    </a>
                    <div class="severity-filters">
                        <span style="font-size: 0.85em; color: rgba(255,255,255,0.7); margin-right: 6px;">Filter:</span>
                        <button class="sev-toggle active" data-severity="error" onclick="toggleSeverity('error', this)">&#x2716; Errors</button>
                        <button class="sev-toggle" data-severity="warning" onclick="toggleSeverity('warning', this)">&#x26A0; Warnings</button>
                    </div>
                </div>
            </div>
        </header>

        <section class="summary">
            <h2>Summary</h2>
            <div class="stats">
                <div class="stat-box stat-box-error">
                    <div class="stat-number stat-number-error">{total_errors}</div>
                    <div class="stat-label">Errors</div>
                </div>
                <div class="stat-box stat-box-warning">
                    <div class="stat-number stat-number-warning">{total_warnings}</div>
                    <div class="stat-label">Warnings</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{len(categories)}</div>
                    <div class="stat-label">Categories</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{len(issues_by_file)}</div>
                    <div class="stat-label">Files Affected</div>
                </div>
            </div>

            {_generate_exclusion_note(total_runtime_excluded) if total_runtime_excluded > 0 else ''}

            {_generate_severity_legend()}

            <h3>Issues by Category</h3>
            <table class="summary-table">
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>Errors</th>
                        <th>Warnings</th>
                        <th>Link</th>
                    </tr>
                </thead>
                <tbody>
                    {_generate_category_summary_rows(all_issues)}
                </tbody>
            </table>
        </section>

        <nav class="toc">
            <h2>Table of Contents</h2>
            <ul>
                <li><a href="#by-category">Issues by Category</a></li>
                <li><a href="#by-file">Issues by File</a></li>
            </ul>
        </nav>

        <section id="by-category">
            <h2>Issues by Category</h2>
            {''.join(category_sections)}
        </section>

        <section id="by-file">
            <h2>Issues by File</h2>
            {''.join(file_sections)}
        </section>

        <footer>
            <p>Generated by KodiDevKit</p>
        </footer>
    </div>
</body>
</html>"""


def _generate_exclusion_note(excluded_count):
    """Generate info note about excluded runtime-generated issues."""
    return f"""
            <div style="background: #e7f3ff; border-left: 4px solid #2196F3; padding: 15px; margin: 20px 0; border-radius: 4px;">
                <p style="margin: 0; color: #1976D2; font-size: 0.95em;">
                    ℹ️ <strong>Note:</strong> {excluded_count} runtime-generated issue{'s' if excluded_count != 1 else ''}
                    from <code>script-skinvariables-*.xml</code> files excluded from this report.
                </p>
            </div>"""


def _generate_severity_legend():
    """Generate a severity level legend box."""
    return """
            <div class="severity-legend">
                <div class="legend-row">
                    <span class="legend-indicator legend-error"></span>
                    <div class="legend-content">
                        <strong>Error</strong> - Must fix.
                        <div class="legend-note">Will cause visible problems in Kodi (blank images, empty labels, broken controls) or will be rejected during repo PR review. Unused variables and includes are errors because the repo review process requires clean definitions with no dead code.</div>
                    </div>
                </div>
                <div class="legend-row">
                    <span class="legend-indicator legend-warning"></span>
                    <div class="legend-content">
                        <strong>Warning</strong> - Skin still works.
                        <div class="legend-note">Kodi silently ignores unknown XML tags and skips unrecognized attributes. Textures.xbt resolves filenames case-insensitively, but skins without packed textures use direct filesystem paths and case mismatches will fail on Linux.</div>
                    </div>
                </div>
            </div>"""


def _generate_category_summary_rows(all_issues):
    """Generate table rows for category summary with error/warning split."""
    rows = []
    for category, issues in sorted(all_issues.items(), key=lambda x: -len(x[1])):
        category_id = category.lower().replace(" ", "-")
        error_count = sum(1 for i in issues if i.get("severity") == SEVERITY_ERROR)
        warning_count = sum(1 for i in issues if i.get("severity") == SEVERITY_WARNING)
        rows.append(f"""
                    <tr>
                        <td><strong>{html.escape(category)}</strong></td>
                        <td><span class="badge badge-error">{error_count}</span></td>
                        <td><span class="badge badge-warning">{warning_count}</span></td>
                        <td><a href="#cat-{category_id}">View →</a></td>
                    </tr>""")
    return ''.join(rows)


def _generate_category_section(category, issues, server_port):
    """Generate HTML section for a category of issues."""
    category_id = category.lower().replace(" ", "-")

    issue_rows = []
    for issue in issues:
        file_path = issue.get("file", "Unknown")
        line = issue.get("line", 0)
        message = issue.get("message", "No message")
        issue_type = issue.get("type", "")
        severity = issue.get("severity", "warning")

        from urllib.parse import quote
        from pathlib import Path

        has_valid_file = file_path and file_path != "Unknown" and os.path.isabs(file_path)

        if has_valid_file:
            localhost_url = f"http://localhost:{server_port}/open?file={quote(file_path)}&line={line}"
            try:
                file_url = Path(file_path).as_uri()
                file_link_html = f'<small style="margin-left: 8px;"><a href="{file_url}" class="alt-link" title="Open file: {html.escape(file_path)}">[file]</a></small>'
            except (ValueError, OSError):
                file_link_html = ""

            file_display = f'<a href="{localhost_url}" class="file-link" target="_blank" title="Open in Sublime Text at line {line}: {html.escape(file_path)}">{html.escape(os.path.basename(file_path))}</a>{file_link_html}'
        else:
            file_display = html.escape(file_path) if file_path else "N/A"

        inc_file = issue.get("include_file", "")

        inc_line = issue.get("include_line", 0)
        if inc_file and inc_line and has_valid_file:
            inc_url = f"http://localhost:{server_port}/open?file={quote(inc_file)}&line={inc_line}"
            inc_basename = os.path.basename(inc_file)
            source_html = f' <a href="{inc_url}" class="file-link inc-source" target="_blank" title="Open {inc_basename} at line {inc_line}">→ {html.escape(inc_basename)}:{inc_line}</a>'
        else:
            source_html = ""

        sev_class = f"severity-{severity}"
        subtype = _classify_subtype(message)
        subtype_html = f'<span class="subtype-tag">{html.escape(subtype)}</span>' if subtype else ""
        issue_rows.append(f"""
                    <tr class="{sev_class}">
                        <td><span class="sev-badge {sev_class}">{html.escape(severity)}</span>{subtype_html}</td>
                        <td>{file_display}</td>
                        <td class="line-number">{line if line else "N/A"}</td>
                        <td>{html.escape(message)}{source_html}</td>
                        <td><code>{html.escape(issue_type)}</code></td>
                    </tr>""")

    desc = CATEGORY_DESCRIPTIONS.get(category, "")
    desc_html = f'\n            <p class="category-desc">{desc}</p>' if desc else ""

    return f"""
        <div class="category-section" id="cat-{category_id}">
            <h3>{html.escape(category)} <span class="badge">{len(issues)}</span></h3>{desc_html}
            <table class="issue-table">
                <thead>
                    <tr>
                        <th>Severity</th>
                        <th>File</th>
                        <th>Line</th>
                        <th>Message</th>
                        <th>Type</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(issue_rows)}
                </tbody>
            </table>
        </div>"""


def _generate_file_section(file_path, issues, server_port):
    """Generate HTML section for issues in a specific file."""
    from pathlib import Path
    from urllib.parse import quote

    has_valid_file = file_path and file_path != "Unknown" and os.path.isabs(file_path)

    if has_valid_file:
        file_name = os.path.basename(file_path)
        try:
            file_link = Path(file_path).as_uri()  # Cross-platform file:// URL
        except (ValueError, OSError):
            file_link = None
    else:
        file_name = file_path if file_path else "Unknown"
        file_link = None

    by_category = defaultdict(list)
    for issue in issues:
        by_category[issue["category"]].append(issue)

    category_groups = []
    for category in sorted(by_category.keys()):
        cat_issues = by_category[category]
        issue_items = []
        for issue in cat_issues:
            line = issue.get("line", 0)
            message = issue.get("message", "No message")
            severity = issue.get("severity", "warning")
            localhost_url = f"http://localhost:{server_port}/open?file={quote(file_path)}&line={line}"

            inc_file = issue.get("include_file", "")
            inc_line = issue.get("include_line", 0)
            if inc_file and inc_line:
                inc_url = f"http://localhost:{server_port}/open?file={quote(inc_file)}&line={inc_line}"
                inc_basename = os.path.basename(inc_file)
                source_html = f' <a href="{inc_url}" class="file-link inc-source" target="_blank" title="Open {inc_basename} at line {inc_line}">→ {html.escape(inc_basename)}:{inc_line}</a>'
            else:
                source_html = ""

            sev_class = f"severity-{severity}"
            subtype = _classify_subtype(message)
            subtype_html = f' <span class="subtype-tag">{html.escape(subtype)}</span>' if subtype else ""
            issue_items.append(f"""
                        <li class="{sev_class}">
                            <span class="sev-badge {sev_class}">{html.escape(severity)}</span>{subtype_html}
                            <a href="{localhost_url}" class="file-link" target="_blank" title="Open in Sublime Text at line {line}">
                                <span class="line-number">Line {line}:</span>
                            </a>
                            {html.escape(message)}{source_html}
                        </li>""")

        category_groups.append(f"""
                <div class="file-category">
                    <h5>{html.escape(category)} ({len(cat_issues)})</h5>
                    <ul class="issue-list">
                        {''.join(issue_items)}
                    </ul>
                </div>""")

    first_line = issues[0].get("line", 1) if issues else 1
    header_localhost_url = f"http://localhost:{server_port}/open?file={quote(file_path)}&line={first_line}"

    file_link_html = f'<small style="margin-left: 8px;"><a href="{file_link}" class="alt-link" title="Open file: {html.escape(file_path)}">[file]</a></small>' if file_link else ''

    return f"""
        <div class="file-section">
            <h4>
                <a href="{header_localhost_url}" class="file-link" target="_blank" title="Open in Sublime Text at line {first_line}">{html.escape(file_name)}</a>
                {file_link_html}
                <span class="badge">{len(issues)} issues</span>
            </h4>
            <div class="file-path"><code>{html.escape(file_path)}</code></div>
            {''.join(category_groups)}
        </div>"""


def _get_css_styles():
    """Return CSS styles for the HTML report."""
    return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
        }

        header h1 {
            font-size: 2.5em;
            margin-bottom: 15px;
        }

        .meta {
            opacity: 0.95;
        }

        .meta p {
            margin: 5px 0;
        }

        .meta code {
            background: rgba(255,255,255,0.2);
            padding: 2px 6px;
            border-radius: 3px;
        }

        .export-button {
            display: inline-block;
            background: rgba(255,255,255,0.2);
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.95em;
            border: 2px solid rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }

        .export-button:hover {
            background: rgba(255,255,255,0.3);
            border-color: rgba(255,255,255,0.5);
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }

        .summary {
            margin-bottom: 40px;
        }

        .summary h2 {
            color: #667eea;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }

        .stat-box {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            border-left: 4px solid #667eea;
        }

        .stat-number {
            font-size: 3em;
            font-weight: bold;
            color: #667eea;
        }

        .stat-label {
            color: #666;
            margin-top: 5px;
            text-transform: uppercase;
            font-size: 0.9em;
            letter-spacing: 1px;
        }

        .summary-table, .issue-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .summary-table th, .issue-table th {
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }

        .summary-table td, .issue-table td {
            padding: 12px;
            border-bottom: 1px solid #e0e0e0;
        }

        .summary-table tr:hover, .issue-table tr:hover {
            background: #f8f9fa;
        }

        .badge {
            background: #667eea;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.9em;
            font-weight: bold;
        }

        .toc {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }

        .toc h2 {
            margin-bottom: 15px;
            color: #667eea;
        }

        .toc ul {
            list-style: none;
        }

        .toc li {
            margin: 8px 0;
        }

        .toc a {
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
        }

        .toc a:hover {
            text-decoration: underline;
        }

        section {
            margin-bottom: 40px;
        }

        section h2 {
            color: #667eea;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }

        .category-section {
            margin-bottom: 30px;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .category-section h3 {
            background: #f8f9fa;
            padding: 15px 20px;
            color: #333;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .file-section {
            margin-bottom: 25px;
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .file-section h4 {
            color: #333;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .file-path {
            color: #666;
            margin-bottom: 15px;
            font-size: 0.9em;
        }

        .file-category {
            margin: 15px 0;
            padding-left: 15px;
            border-left: 3px solid #667eea;
        }

        .file-category h5 {
            color: #667eea;
            margin-bottom: 10px;
        }

        .issue-list {
            list-style: none;
            padding-left: 0;
        }

        .issue-list li {
            padding: 8px 0;
            border-bottom: 1px solid #f0f0f0;
        }

        .issue-list li:last-child {
            border-bottom: none;
        }

        .line-number {
            color: #999;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            font-weight: bold;
        }

        .issue-list li a .line-number {
            color: #667eea;
            text-decoration: none;
        }

        .issue-list li a:hover .line-number {
            text-decoration: underline;
        }

        .file-link {
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
        }

        .file-link:hover {
            text-decoration: underline;
        }

        .alt-link {
            color: #999;
            font-size: 0.85em;
            text-decoration: none;
        }

        .alt-link:hover {
            color: #667eea;
            text-decoration: underline;
        }

        code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }

        footer {
            text-align: center;
            padding: 20px;
            color: #999;
            border-top: 1px solid #e0e0e0;
            margin-top: 40px;
        }

        footer a {
            color: #667eea;
            text-decoration: none;
        }

        footer a:hover {
            text-decoration: underline;
        }

        .sev-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75em;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .subtype-tag {
            display: inline-block;
            margin-top: 3px;
            padding: 1px 6px;
            border-radius: 3px;
            font-size: 0.65em;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            background: #e8eaf6;
            color: #3949ab;
            white-space: nowrap;
        }

        /* In table cells, stack badge + subtype vertically */
        td .subtype-tag {
            display: block;
            margin-top: 3px;
            width: fit-content;
        }

        .sev-badge.severity-error {
            background: #ffebee;
            color: #c62828;
        }

        .sev-badge.severity-warning {
            background: #fff3e0;
            color: #e65100;
        }

        tr.severity-error {
            border-left: 3px solid #c62828;
        }

        tr.severity-warning {
            border-left: 3px solid #e65100;
        }

        .severity-filters {
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .sev-toggle {
            padding: 5px 14px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 4px;
            background: rgba(255,255,255,0.08);
            color: rgba(255,255,255,0.4);
            cursor: pointer;
            font-size: 0.8em;
            font-weight: bold;
            transition: all 0.15s;
            text-decoration: line-through;
        }

        .sev-toggle.active {
            background: rgba(255,255,255,0.25);
            color: white;
            border-color: rgba(255,255,255,0.7);
            text-decoration: none;
        }

        .sev-toggle:hover {
            background: rgba(255,255,255,0.3);
        }

        .inc-source {
            font-size: 0.85em;
            opacity: 0.85;
            margin-left: 4px;
            color: #667eea;
        }

        .stat-box-error {
            border-left-color: #c62828;
        }

        .stat-box-warning {
            border-left-color: #e65100;
        }

        .stat-number-error {
            color: #c62828;
        }

        .stat-number-warning {
            color: #e65100;
        }

        .badge-error {
            background: #c62828;
        }

        .badge-warning {
            background: #e65100;
        }

        .severity-legend {
            background: #f8f9fa;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 16px 20px;
            margin: 20px 0;
        }

        .legend-row {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 8px 0;
            font-size: 0.92em;
            color: #444;
        }

        .legend-row + .legend-row {
            border-top: 1px solid #e8e8e8;
        }

        .legend-content {
            flex: 1;
        }

        .legend-note {
            margin-top: 6px;
            padding: 8px 12px;
            background: #eef0f5;
            border-radius: 4px;
            font-size: 0.88em;
            color: #555;
            line-height: 1.5;
        }

        .legend-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 2px;
            flex-shrink: 0;
            margin-top: 4px;
        }

        .legend-error {
            background: #c62828;
        }

        .legend-warning {
            background: #e65100;
        }

        .category-desc {
            padding: 8px 20px 12px;
            font-size: 0.88em;
            color: #666;
            line-height: 1.5;
        }

        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }

            header h1 {
                font-size: 1.8em;
            }

            .stats {
                grid-template-columns: 1fr;
            }

            .summary-table, .issue-table {
                font-size: 0.9em;
            }
        }
    """
