"""
Test base classes and centralized imports.

This module provides a single point of maintenance for all test imports.
When refactoring code, only update imports here - all tests inherit from base classes.
"""

import unittest
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================================
# VALIDATION IMPORTS
# ============================================================================
# When validation classes are renamed, update ONLY here
from libs.validation import ValidationVariable as VariableCheck  # Alias for test compatibility
from libs.validation import ValidationLabel as LabelCheck  # Alias for test compatibility
from libs.validation import ValidationIds as IdCheck  # Alias for test compatibility
from libs.validation import ValidationFont as FontCheck  # Alias for test compatibility
from libs.validation import ValidationImage as ImageCheck  # Alias for test compatibility
from libs.validation import ValidationInclude as IncludeCheck  # Alias for test compatibility
from libs.validation import ValidationExpression as ExpressionCheck  # Alias for test compatibility
from libs.validation import XmlInterpreter
from libs.validation import Context


# ============================================================================
# SKIN IMPORTS
# ============================================================================
from libs.skin.skin import Skin
from libs.skin.resolution import SkinResolution
from libs.skin.maps import SkinMaps
from libs.skin.include import SkinInclude


# ============================================================================
# ADDON IMPORTS
# ============================================================================
from libs.addon import Addon


# ============================================================================
# UTILS IMPORTS
# ============================================================================
from libs import utils


# ============================================================================
# BASE TEST CLASSES
# ============================================================================

class KodiDevKitTestCase(unittest.TestCase):
    """
    Base test class for all KodiDevKit tests.

    Provides common setup and utilities for testing.
    All imports available as class attributes.
    """

    # Validation classes
    VariableCheck = VariableCheck
    LabelCheck = LabelCheck
    IdCheck = IdCheck
    FontCheck = FontCheck
    ImageCheck = ImageCheck
    IncludeCheck = IncludeCheck
    ExpressionCheck = ExpressionCheck
    XmlInterpreter = XmlInterpreter
    Context = Context

    # Skin classes
    Skin = Skin
    IncludeResolver = SkinResolution
    IncludeMaps = SkinMaps
    Include = SkinInclude

    # Addon classes
    Addon = Addon

    # Utils
    utils = utils


class ValidationTestCase(KodiDevKitTestCase):
    """Base class specifically for validation tests."""
    pass


class SkinTestCase(KodiDevKitTestCase):
    """Base class specifically for skin tests."""
    pass


# Module-level aliases for backward compatibility (match class attributes)
IncludeResolver = SkinResolution
IncludeMaps = SkinMaps
Include = SkinInclude

__all__ = [
    'KodiDevKitTestCase',
    'ValidationTestCase',
    'SkinTestCase',
    # Validation
    'VariableCheck',
    'LabelCheck',
    'IdCheck',
    'FontCheck',
    'ImageCheck',
    'IncludeCheck',
    'ExpressionCheck',
    'XmlInterpreter',
    'Context',
    # Skin
    'Skin',
    # Backward-compatible aliases (kept for test compatibility):
    'IncludeResolver',  # noqa: F822 - Alias for SkinResolution
    'IncludeMaps',      # noqa: F822 - Alias for SkinMaps
    'Include',          # noqa: F822 - Alias for SkinInclude
    # Addon
    'Addon',
    # Utils
    'utils',
]
