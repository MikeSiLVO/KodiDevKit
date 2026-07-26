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


from libs.validation import ValidationVariable as VariableCheck
from libs.validation import ValidationLabel as LabelCheck
from libs.validation import ValidationIds as IdCheck
from libs.validation import ValidationFont as FontCheck
from libs.validation import ValidationImage as ImageCheck
from libs.validation import ValidationInclude as IncludeCheck
from libs.validation import ValidationExpression as ExpressionCheck
from libs.validation import XmlInterpreter
from libs.validation import Context


from libs.skin.skin import Skin
from libs.skin.include import SkinInclude


from libs.addon import Addon


from libs import utils


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
    Include = SkinInclude

    # Addon classes
    Addon = Addon

    utils = utils


class ValidationTestCase(KodiDevKitTestCase):
    """Base class specifically for validation tests."""
    pass


class SkinTestCase(KodiDevKitTestCase):
    """Base class specifically for skin tests."""
    pass


Include = SkinInclude

__all__ = [
    'KodiDevKitTestCase',
    'ValidationTestCase',
    'SkinTestCase',
    'VariableCheck',
    'LabelCheck',
    'IdCheck',
    'FontCheck',
    'ImageCheck',
    'IncludeCheck',
    'ExpressionCheck',
    'XmlInterpreter',
    'Context',
    'Skin',
    'Include',          # noqa: F822
    'Addon',
    'utils',
]
