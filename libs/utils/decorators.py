"""Decorators for backgrounding and busy-guarding plugin commands."""

from __future__ import annotations

import logging
import threading
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True




def run_async(func: Callable[..., Any]) -> Callable[..., Any]:
    """Run function in background thread to avoid blocking Sublime Text UI."""
    @wraps(func)
    def async_func(*args: Any, **kwargs: Any) -> threading.Thread:
        thread_name = f"KodiDevKit.{func.__name__}"
        func_hl = threading.Thread(
            target=func,
            args=args,
            kwargs=kwargs,
            name=thread_name,
            daemon=True
        )
        func_hl.start()
        return func_hl
    return async_func


def check_busy(func: Callable[..., Any]) -> Callable[..., Any]:
    """Prevent concurrent execution by checking self.is_busy flag."""
    @wraps(func)
    def decorator(self: Any, *args: Any, **kwargs: Any) -> Any:
        if getattr(self, "is_busy", False):
            logger.critical("Already busy. Please wait.")
            return None
        self.is_busy = True
        try:
            return func(self, *args, **kwargs)
        finally:
            self.is_busy = False
    return decorator
