"""Hook behavior modes, and which shell commands the commit gate applies to.

A mode decides whether a lifecycle hook may deny an action. The installed host
entry carries its mode as ``--mode``; the environment can override it without
reinstalling, and ``LAZYPLAN_NO_HOOKS`` silences everything.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterator, Mapping

EVENTS = (
    "session-start",
    "prompt-submit",
    "pre-tool",
    "post-tool",
    "stop",
    "session-end",
    "pre-compact",
)
MODES = ("strict", "advisory", "off")
DEFAULT_MODE = "strict"
MODE_ENV = "LAZYPLAN_HOOKS"
NO_HOOKS_ENV = "LAZYPLAN_NO_HOOKS"

_OPERATOR_CHARS = ";&|()\n"
_COMMAND_PREFIXES = frozenset(
    {"!", "{", "if", "then", "else", "elif", "do", "while", "until"}
    | {"builtin", "command", "env", "exec", "nohup", "sudo", "time"}
)
_GIT_OPTIONS_WITH_VALUE = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix"}
)
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_LOOSE_COMMIT = re.compile(
    r"(?:^|[;&|({\n])\s*(?:[A-Za-z_]\w*=\S*\s+)*(?:\S*[\\/])?git(?:\.exe)?"
    r"(?:\s+(?:-[Cc]\s+\S+|-\S+))*\s+commit(?![\w-])",
    re.IGNORECASE,
)


def normalize_mode(text: object, default: str = DEFAULT_MODE) -> str:
    """Return one of :data:`MODES`, falling back to *default*."""
    body = str(text or "").strip().lower()
    return body if body in MODES else default


def mode_from_env(environ: Mapping[str, str]) -> str | None:
    """Mode requested by the environment, or None when it is unset or invalid."""
    if str(environ.get(NO_HOOKS_ENV, "")).strip():
        return "off"
    wanted = str(environ.get(MODE_ENV, "")).strip().lower()
    return wanted if wanted in MODES else None


def resolve_mode(flag: str | bool | None, stored: str, environ: Mapping[str, str]) -> str:
    """Resolve one mode: environment, then explicit flag, then stored state."""
    if flag is False or str(environ.get(NO_HOOKS_ENV, "")).strip():
        return "off"
    if isinstance(flag, str) and flag:
        explicit = normalize_mode(flag, "")
        if explicit:
            return explicit
    from_env = mode_from_env(environ)
    if from_env is not None:
        return from_env
    return normalize_mode(stored)


def is_git_commit(command: str) -> bool:
    """True when a shell command line runs ``git commit`` as one of its commands.

    Quoted text and the arguments of other programs never count, so a search
    for the words is not a commit. A line the tokenizer cannot parse, such as a
    heredoc body with a lone apostrophe, falls back to a command-start pattern.
    """
    try:
        words = _shell_words(command)
    except ValueError:
        return bool(_LOOSE_COMMIT.search(command))
    return any(_runs_git_commit(simple) for simple in _simple_commands(words))


def _shell_words(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=_OPERATOR_CHARS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    return list(lexer)


def _simple_commands(words: list[str]) -> Iterator[list[str]]:
    current: list[str] = []
    for word in words:
        if word == "}" or (word and all(char in _OPERATOR_CHARS for char in word)):
            if current:
                yield current
            current = []
        else:
            current.append(word)
    if current:
        yield current


def _runs_git_commit(words: list[str]) -> bool:
    index = 0
    while index < len(words) and (
        words[index] in _COMMAND_PREFIXES or _ASSIGNMENT.match(words[index])
    ):
        index += 1
    if index == len(words) or _program_name(words[index]) != "git":
        return False
    return _git_subcommand(words[index + 1 :]) == "commit"


def _program_name(word: str) -> str:
    name = re.split(r"[\\/]", word)[-1].lower()
    return name.removesuffix(".exe")


def _git_subcommand(args: list[str]) -> str:
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in _GIT_OPTIONS_WITH_VALUE:
            index += 2
        elif arg.startswith("-"):
            index += 1
        else:
            return arg
    return ""
