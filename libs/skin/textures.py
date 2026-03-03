"""
Texture packing utilities for Kodi skins.

This module provides functionality to run TexturePacker on skin media directories.
"""

import os
import subprocess
import platform
import logging

logger = logging.getLogger("KodiDevKit.skin.textures")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def texturepacker(media_path, settings, xbt_filename="Textures.xbt"):
    """
    Run TexturePacker on media_path.

    Args:
        media_path: Path to media directory containing skin images
        settings: Settings object with texturepacker_path configuration
        xbt_filename: Output XBT filename (default: "Textures.xbt")

    Returns:
        None
    """
    tp_path = settings.get("texturepacker_path")
    if not tp_path:
        return None
    args = ['-dupecheck',
            '-input "%s"' % media_path,
            '-output "%s"' % os.path.join(media_path, xbt_filename)]
    if platform.system() == "Linux":
        args = ['%s %s' % (tp_path, " ".join(args))]
    else:
        args.insert(0, tp_path)
    with subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True,
        shell=True,
    ) as p:
        if p.stdout:
            for line in p.stdout:
                logger.warning(line)
