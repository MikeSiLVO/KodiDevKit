"""Run every test with the sublime stub installed and the package on sys.path."""

import sys
import os

# stub sublime before any import that reads it
tests_dir = os.path.dirname(os.path.abspath(__file__))
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)

import mock_sublime
sys.modules['sublime'] = mock_sublime
sys.modules['sublime_api'] = mock_sublime

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

# the package's parent too, for KodiDevKit.libs imports
parent_dir = os.path.dirname(package_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import unittest

loader = unittest.TestLoader()
start_dir = os.path.dirname(os.path.abspath(__file__))
suite = loader.discover(start_dir, pattern='test_*.py')

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

sys.exit(not result.wasSuccessful())
