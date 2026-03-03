"""Decorator utilities for KodiDevKit."""

from __future__ import annotations

import logging
import threading
import time
from functools import wraps
from typing import Any, Callable, Type

logger = logging.getLogger("KodiDevKit.utils.decorators")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def retry(
    exception_to_check: Type[Exception],
    tries: int = 4,
    delay: int = 3,
    backoff: int = 2
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Retry function on exception with exponential backoff."""
    def deco_retry(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def f_retry(*args: Any, **kwargs: Any) -> Any:
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exception_to_check as e:
                    logger.info(f"{e}, Retrying in {mdelay} seconds...")
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)
        return f_retry
    return deco_retry


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
