"""Texture packing utilities: runs TexturePacker on skin media directories."""

import os
import subprocess
import logging

logger = logging.getLogger("KodiDevKit.skin.textures")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def texturepacker(media_path, settings, xbt_filename="Textures.xbt"):
    """Run TexturePacker on `media_path`, writing the output to `xbt_filename` there."""
    tp_path = settings.get("texturepacker_path")
    if not tp_path:
        return None
    args = ['-dupecheck',
            '-input "%s"' % media_path,
            '-output "%s"' % os.path.join(media_path, xbt_filename)]
    from ..utils import get_platform
    if get_platform() == "linux":
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
