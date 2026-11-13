"""Map one code line to semantic highlight spans.

Pygments tokenizes the line; the diff renderer maps each span kind to a theme
colour. Lexers and lines are cached so scrolling a long diff stays responsive.
"""

from __future__ import annotations

from functools import lru_cache

from pygments.lexer import Lexer
from pygments.lexers import get_lexer_for_filename
from pygments.token import Token, _TokenType
from pygments.util import ClassNotFound

HighlightSpan = tuple[str, str]

_TOKEN_KINDS: tuple[tuple[_TokenType, str], ...] = (
    (Token.Comment, "comment"),
    (Token.Keyword, "keyword"),
    (Token.Generic.Heading, "keyword"),
    (Token.Generic.Subheading, "keyword"),
    (Token.Literal.String, "string"),
    (Token.Name.Tag, "string"),
    (Token.Literal.Number, "number"),
    (Token.Name.Function, "function"),
    (Token.Name.Class, "class"),
    (Token.Name.Builtin, "builtin"),
    (Token.Name.Decorator, "decorator"),
    (Token.Operator, "operator"),
    (Token.Punctuation, "punct"),
)


def _kind(token: _TokenType) -> str:
    """Semantic span kind for one Pygments token type."""
    for parent, name in _TOKEN_KINDS:
        if token in parent:
            return name
    return "text"


@lru_cache(maxsize=256)
def _lexer(path: str) -> Lexer | None:
    """Lexer for a path suffix, or None when Pygments has no match."""
    try:
        return get_lexer_for_filename(path, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return None


@lru_cache(maxsize=4096)
def highlight_line(path: str, text: str) -> tuple[HighlightSpan, ...]:
    """Return ``(kind, text)`` spans for one line, or one plain span."""
    if not text:
        return ()
    lexer = _lexer(path)
    if lexer is None:
        return (("text", text),)
    added_newline = not text.endswith("\n")
    source = f"{text}\n" if added_newline else text
    try:
        spans = [(_kind(token), value) for _, token, value in lexer.get_tokens_unprocessed(source)]
    except Exception:  # A lexer failure must never hide the diff.
        return (("text", text),)
    if added_newline and spans:
        kind, value = spans[-1]
        value = value[:-1] if value.endswith("\n") else value
        if value:
            spans[-1] = (kind, value)
        else:
            spans.pop()
    return tuple(spans) or (("text", text),)


def clear_highlight_cache() -> None:
    """Drop cached lexers and lines (tests and explicit refresh)."""
    _lexer.cache_clear()
    highlight_line.cache_clear()
