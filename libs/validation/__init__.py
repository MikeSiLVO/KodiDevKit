"""Validation package for Kodi skin checking."""
from .font import ValidationFont
from .image import ValidationImage
from .ids import ValidationIds
from .label import ValidationLabel
from .include import ValidationInclude
from .variable import ValidationVariable
from .expression import ValidationExpression
from .filecheck import ValidationFileCheck
from .interpreter import XmlInterpreter, Context

# Import constants for external use
from .constants import (
    CONTROL_TAGS,
    BRACKET_TAGS,
    INCLUDE_DEFINITION_TAGS,
    NOOP_TAGS,
    POS_TAGS,
    SINGLETON_TAGS,
    ALLOWED_MULTI,
    ALLOWED_VALUES,
    CASE_INSENSITIVE_ENUMS,
    PARSER,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)

# Import hierarchy data
from .hierarchy import (
    WINDOW_CHILDREN,
    CONTROLS_CHILDREN,
    GROUP_TYPES,
    CONTAINER_TYPES,
    ALL_LAYOUT_TAGS,
)

__all__ = [
    'ValidationFont',
    'ValidationImage',
    'ValidationIds',
    'ValidationLabel',
    'ValidationInclude',
    'ValidationVariable',
    'ValidationExpression',
    'ValidationFileCheck',
    'XmlInterpreter',
    'Context',
    # Constants
    'CONTROL_TAGS',
    'BRACKET_TAGS',
    'INCLUDE_DEFINITION_TAGS',
    'NOOP_TAGS',
    'POS_TAGS',
    'SINGLETON_TAGS',
    'ALLOWED_MULTI',
    'ALLOWED_VALUES',
    'CASE_INSENSITIVE_ENUMS',
    'PARSER',
    'SEVERITY_ERROR',
    'SEVERITY_WARNING',
    # Hierarchy
    'WINDOW_CHILDREN',
    'CONTROLS_CHILDREN',
    'GROUP_TYPES',
    'CONTAINER_TYPES',
    'ALL_LAYOUT_TAGS',
]
