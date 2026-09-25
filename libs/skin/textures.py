"""Texture packing utilities: runs TexturePacker on skin media directories."""

import os
import subprocess
import logging

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def texturepacker(media_path, settings, xbt_filename="Textures.xbt"):
    """Run TexturePacker over the media folder, writing the .xbt into it."""
    tp_path = settings.get("texturepacker_path")
    if not tp_path:
        return None
    args = [tp_path, "-dupecheck",
            "-input", media_path,
            "-output", os.path.join(media_path, xbt_filename)]
    with subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True,
    ) as p:
        if p.stdout:
            for line in p.stdout:
                logger.warning(line)
