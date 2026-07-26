"""Type stubs for mdpopups."""

from typing import Any, Optional
import sublime

def show_popup(
    view: sublime.View,
    content: str,
    md: bool = True,
    css: Optional[str] = None,
    flags: int = 0,
    location: int = -1,
    max_width: int = 320,
    max_height: int = 240,
    on_navigate: Optional[Any] = None,
    on_hide: Optional[Any] = None,
) -> None: ...

def hide_popup(view: sublime.View) -> None: ...
def is_popup_visible(view: sublime.View) -> bool: ...
def syntax_highlight(view: sublime.View, src: str, language: str = "", **kwargs: Any) -> str: ...
