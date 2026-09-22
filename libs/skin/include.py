"""SkinInclude: one <include> definition plus Kodi's constant/expression whitelists."""

from __future__ import annotations

from lxml import etree as ET
import os


class SkinInclude(dict):
    """One include, variable or default definition, read through dict-style keys."""

    # where constants and expressions expand, mirrored from GUIIncludes.cpp
    constant_attribs = frozenset({
        "acceleration", "border", "center", "delay", "end", "h", "height", "max",
        "min", "repeat", "start", "time", "w", "width", "x", "y",
    })

    constant_nodes = frozenset({
        "bordersize", "bottom", "centerbottom", "centerleft", "centerright", "centertop",
        "depth", "fadetime", "focusposition", "height", "itemgap", "left",
        "movement", "offsetx", "offsety", "pauseatend", "posx", "posy",
        "radioheight", "radioposx", "radioposy", "radiowidth", "right", "sliderheight",
        "sliderwidth", "spinheight", "spinposx", "spinposy", "spinwidth", "textoffsetx",
        "textoffsety", "textwidth", "timeperimage", "top", "width",
    })

    exp_nodes = frozenset({"enable", "selected", "usealttexture", "visible"})
    exp_attribs = frozenset({"condition"})

    def __init__(self, node, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.node = node

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
            return self.content
        elif key == "length":
            return self.length
        return super().__getitem__(key)

    def get(self, key, default=None):
        """Dict get that also reaches the node-backed keys."""
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    @property
    def line(self):
        """Source line of the definition."""
        return self.node.sourceline

    @property
    def tag(self):
        """Tag of the wrapped node, exposed as the "type" key."""
        return self.node.tag

    @property
    def content(self):
        """Splice body wrapped in <root>: <definition> children, else every child but <param>."""
        definition = self.node.find("definition")
        if definition is not None:
            children_xml = "".join(
                ET.tostring(child, pretty_print=True, encoding="unicode")
                for child in definition
            )
        else:
            children_xml = "".join(
                ET.tostring(child, pretty_print=True, encoding="unicode")
                for child in self.node
                if child.tag != "param"
            )

        return f"<root>{children_xml}</root>"

    @property
    def name(self):
        """The name attribute, None for a default block."""
        return self.node.attrib.get("name")

    @property
    def filename(self):
        """Basename of the file the definition lives in."""
        return os.path.basename(self.file)

