"""Helpers shared by the tests."""


def kodi_resolve(skin, node, folder):
    """Resolve an XML tree in place, the way Kodi resolves a window."""
    skin.resolver.resolve(node, folder)
