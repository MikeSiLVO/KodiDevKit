"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting
using Sublime Text 4
"""

from __future__ import annotations

from lxml import etree as ET
import os


class SkinInclude(dict):
    """
    Represents an include-like kodi object.

    Constant whitelists match Kodi's CGUIIncludes exactly (GUIIncludes.cpp lines 18-50).
    These define which attributes and node text values can have constants expanded.
    """
    # CONSTANT_ATTRIBUTES from Kodi source (sorted for binary search)
    constant_attribs = frozenset({
        "acceleration", "border", "center", "delay", "end", "h", "height", "max",
        "min", "repeat", "start", "time", "w", "width", "x", "y",
    })

    # CONSTANT_NODES from Kodi source (sorted for binary search)
    constant_nodes = frozenset({
        "bordersize", "bottom", "centerbottom", "centerleft", "centerright", "centertop",
        "depth", "fadetime", "focusposition", "height", "itemgap", "left",
        "movement", "offsetx", "offsety", "pauseatend", "posx", "posy",
        "radioheight", "radioposx", "radioposy", "radiowidth", "right", "sliderheight",
        "sliderwidth", "spinheight", "spinposx", "spinposy", "spinwidth", "textoffsetx",
        "textoffsety", "textwidth", "timeperimage", "top", "width",
    })

    # EXPRESSION_NODES and EXPRESSION_ATTRIBUTE from Kodi source
    exp_nodes = frozenset({"enable", "selected", "usealttexture", "visible"})
    exp_attribs = frozenset({"condition"})

    def __init__(self, node, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.node = node

        # Validate and store file path
        file_path = kwargs.get("file")
        if not file_path or not isinstance(file_path, str):
            raise ValueError("Include requires 'file' argument as string")
        self.file: str = file_path

        if self.node.getnext() is not None:
            self.length = self.node.getnext().sourceline - self.node.sourceline
        else:
            self.length = None

    def __getitem__(self, key):
        if key == "line":
            return self.line
        elif key == "type":
            return self.tag
        elif key == "name":
            return self.name
        elif key == "filename":
            return self.filename
        elif key == "file":
            return self.file
        elif key == "content":
            return self.content  # Use the property to get correct content
        elif key == "length":
            return self.length
        return super().__getitem__(key)

    def get(self, key):
        return self.__getitem__(key)

    @property
    def line(self):
        """
        returns xml source line
        """
        return self.node.sourceline

    @property
    def tag(self):
        """
        returns tag of include node
        """
        return self.node.tag

    @property
    def content(self):
        """
        Returns include content to be spliced into calling window.
        Matches Kodi's behavior:
        - If <definition> tag exists: return only its children (parameterized format)
        - Otherwise: return direct children excluding <param> tags (legacy format)

        Note: Wraps multiple children in <root> tag to create valid XML for parsing.
        """
        # Check for <definition> tag (new parameterized include format)
        definition = self.node.find("definition")
        if definition is not None:
            # Extract only the children inside <definition>
            children_xml = "".join(
                ET.tostring(child, pretty_print=True, encoding="unicode")
                for child in definition
            )
        else:
            # Legacy format: extract direct children, skip <param> tags
            children_xml = "".join(
                ET.tostring(child, pretty_print=True, encoding="unicode")
                for child in self.node
                if child.tag != "param"
            )

        # Wrap in <root> to ensure valid XML (single root element required)
        # The resolver will extract the children when splicing
        return f"<root>{children_xml}</root>"

    @property
    def name(self):
        """
        returns name of include
        """
        return self.node.attrib.get("name")

    @property
    def filename(self):
        """
        returns filename of include parent file
        """
        return os.path.basename(self.file)

