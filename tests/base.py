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


from libs.validation.variable import ValidationVariable as VariableCheck
from libs.validation.label import ValidationLabel as LabelCheck
from libs.validation.ids import ValidationIds as IdCheck
from libs.validation.font import ValidationFont as FontCheck
from libs.validation.image import ValidationImage as ImageCheck
from libs.validation.include import ValidationInclude as IncludeCheck
from libs.validation.skinmap import ValidationMap as MapCheck
from libs.validation.interpreter import XmlInterpreter
from libs.validation.interpreter import Context


from libs.skin.skin import Skin
from libs.skin.include import SkinInclude


from libs.addon.addon import Addon


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
    MapCheck = MapCheck
    XmlInterpreter = XmlInterpreter
    Context = Context

    # Skin classes
    Skin = Skin
    Include = SkinInclude

    # Addon classes
    Addon = Addon


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
    'MapCheck',
    'XmlInterpreter',
    'Context',
    'Skin',
    'Include',          # noqa: F822
    'Addon',
]
