"""
KodiDevKit utilities package.

This package provides organized utility functions for Kodi skinning development.
All functions are re-exported at the package level for backward compatibility.
"""

# Re-export all functions from submodules
from .colors import (
    is_kodi_hex,
    to_hex,
    get_contrast_color,
)

from .decorators import (
    retry,
    run_async,
    check_busy,
)

from .expressions import (
    is_number,
    extract_number_value,
    extract_variable_name,
    resolve_params_in_text,
    is_dynamic_expression,
    starts_with_param_reference,
    contains_dynamic_expression,
    get_param_names_in_context,
)

from .files import (
    eol_info_from_path_patterns,
    save_xml,
    get_sublime_path,
    get_absolute_file_paths,
    make_archive,
    check_bom,
    check_paths,
    get_addons,
)

from .xml import (
    _parse_xml_file,
    get_root_from_file,
    check_brackets,
    file_needs_expansion,
    tree_needs_expansion,
    PARSER,
    FILE_PREVIEW_SIZE,
    last_xml_errors,
    _xml_parse_cache,
)

from .validation import (
    is_runtime_generated_file,
    normalize_control_id,
    create_issue,
    resolve_param_in_name,
    get_all_parameter_contexts,
    deduplicate_issues,
    should_report_progress,
    find_unused_items,
    find_undefined_items,
    resolve_include_content,
    _get_font_name_pattern,
    find_font_line_in_include,
    find_skinshortcuts_template,
    find_includes_in_skinshortcuts_template,
    find_variables_in_skinshortcuts_template,
    find_variable_definitions_in_skinshortcuts_template,
)

from ..addon.translations import (
    get_po_file,
    create_new_po_file,
    convert_xml_to_po,
)

from .sublime_helpers import (
    find_word,
    get_node_content,
    jump_to_label_declaration,
    prettyprint,
    debug_print,
)

__all__ = [
    # colors
    "is_kodi_hex",
    "to_hex",
    "get_contrast_color",
    # decorators
    "retry",
    "run_async",
    "check_busy",
    # expressions
    "is_number",
    "extract_number_value",
    "extract_variable_name",
    "resolve_params_in_text",
    "is_dynamic_expression",
    "starts_with_param_reference",
    "contains_dynamic_expression",
    "get_param_names_in_context",
    # files
    "eol_info_from_path_patterns",
    "save_xml",
    "get_sublime_path",
    "get_absolute_file_paths",
    "make_archive",
    "check_bom",
    "check_paths",
    "get_addons",
    # xml
    "_parse_xml_file",
    "get_root_from_file",
    "check_brackets",
    "file_needs_expansion",
    "tree_needs_expansion",
    "PARSER",
    "FILE_PREVIEW_SIZE",
    "last_xml_errors",
    "_xml_parse_cache",
    # validation
    "is_runtime_generated_file",
    "normalize_control_id",
    "create_issue",
    "resolve_param_in_name",
    "get_all_parameter_contexts",
    "deduplicate_issues",
    "should_report_progress",
    "find_unused_items",
    "find_undefined_items",
    "resolve_include_content",
    "_get_font_name_pattern",
    "find_font_line_in_include",
    "find_skinshortcuts_template",
    "find_includes_in_skinshortcuts_template",
    "find_variables_in_skinshortcuts_template",
    "find_variable_definitions_in_skinshortcuts_template",
    # po_helpers
    "get_po_file",
    "create_new_po_file",
    "convert_xml_to_po",
    # sublime_helpers
    "find_word",
    "get_node_content",
    "jump_to_label_declaration",
    "prettyprint",
    "debug_print",
]
