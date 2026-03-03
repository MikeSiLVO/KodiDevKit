"""
Test runner for KodiDevKit tests.
Runs tests with appropriate Python environment.
"""

import sys
import os

# Mock the sublime module before any imports that might use it
tests_dir = os.path.dirname(os.path.abspath(__file__))
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)

import mock_sublime
sys.modules['sublime'] = mock_sublime
sys.modules['sublime_api'] = mock_sublime  # Also mock the C extension

# Add package directory
package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

# Also add the parent of package directory so "KodiDevKit.libs" imports work
parent_dir = os.path.dirname(package_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import unittest

# Discover and run all tests
loader = unittest.TestLoader()
start_dir = os.path.dirname(os.path.abspath(__file__))
suite = loader.discover(start_dir, pattern='test_*.py')

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

# Exit with error code if tests failed
sys.exit(not result.wasSuccessful())
