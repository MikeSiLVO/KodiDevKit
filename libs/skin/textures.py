"""Texture packing utilities: runs TexturePacker on skin media directories."""

import os
import subprocess
import logging

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def texturepacker(media_path, settings, output_path=None):
    """Run TexturePacker over the folder into its Textures.xbt or a given path; True on success."""
    tp_path = settings.get("texturepacker_path")
    if not tp_path:
        return False
    args = [tp_path, "-dupecheck",
            "-input", media_path,
            "-output", output_path or os.path.join(media_path, "Textures.xbt")]
    try:
        with subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
        ) as p:
            if p.stdout:
                for line in p.stdout:
                    logger.warning(line)
    except OSError as e:
        logger.error("TexturePacker could not run: %s", e)
        return False
    return p.returncode == 0
