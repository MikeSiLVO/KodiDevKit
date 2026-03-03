"""
Test utilities and helpers for KodiDevKit tests.

This module provides centralized helper functions for common test operations.
If internal package structure changes, only this file needs updating.
"""


def kodi_resolve(skin, node, folder):
    """
    Resolve a node using Kodi's resolution engine.

    Wrapper around the actual resolution implementation so tests don't couple
    to internal package structure.

    Args:
        skin: Skin instance
        node: XML node to resolve
        folder: Folder context (e.g., "16x9")
    """
    skin.resolver.resolve(node, folder)
