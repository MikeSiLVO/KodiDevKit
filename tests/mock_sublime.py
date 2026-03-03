"""
Mock sublime module for unit testing.
Provides minimal implementations of sublime API used by InfoProvider.
"""
import os


class MockSettings:
    """Mock implementation of sublime Settings object."""

    def __init__(self):
        self._settings = {}

    def get(self, key, default=None):
        """Get a setting value."""
        return self._settings.get(key, default)

    def set(self, key, value):
        """Set a setting value."""
        self._settings[key] = value


def load_settings(name):
    """Mock load_settings - returns empty settings."""
    return MockSettings()


def load_resource(resource_path):
    """
    Mock load_resource - loads actual files from the data directory.
    Converts Packages/KodiDevKit/... paths to real filesystem paths.
    """
    if resource_path.startswith("Packages/KodiDevKit/"):
        relative_path = resource_path.replace("Packages/KodiDevKit/", "")
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        package_dir = os.path.dirname(tests_dir)
        file_path = os.path.join(package_dir, relative_path)

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            raise OSError(f"Resource not found: {resource_path}")

    raise OSError(f"Invalid resource path: {resource_path}")


def error_message(message):
    """Mock error_message - just print for testing."""
    print(f"SUBLIME ERROR: {message}")


# Module-level constants that might be used
ENCODED_POSITION = 1
TRANSIENT = 2
FORCE_GROUP = 4
