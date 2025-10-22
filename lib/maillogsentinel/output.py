"""Console output helpers for MailLogSentinel CLI tools."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional


ANSI_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
}


@dataclass
class OutputOptions:
    color: bool = True
    stream: any = sys.stdout


def detect_color_support(stream: any = sys.stdout) -> bool:
    if not hasattr(stream, "isatty"):
        return False
    try:
        return stream.isatty()
    except Exception:
        return False


def apply_color(text: str, color: str, *, options: OutputOptions) -> str:
    if not options.color:
        return text
    code = ANSI_CODES.get(color)
    if not code:
        return text
    return f"{code}{text}{ANSI_CODES['reset']}"


def heading(text: str, *, options: OutputOptions, level: int = 1) -> None:
    prefix = "#" * level
    styled = apply_color(f"{prefix} {text}", "cyan", options=options)
    print(styled, file=options.stream)


def info(text: str, *, options: OutputOptions) -> None:
    print(apply_color(text, "gray", options=options), file=options.stream)


def success(text: str, *, options: OutputOptions) -> None:
    print(apply_color(text, "green", options=options), file=options.stream)


def warning(text: str, *, options: OutputOptions) -> None:
    print(apply_color(text, "yellow", options=options), file=options.stream)


def error(text: str, *, options: OutputOptions) -> None:
    print(apply_color(text, "red", options=options), file=options.stream)


def divider(*, options: OutputOptions) -> None:
    print(apply_color("=" * 72, "gray", options=options), file=options.stream)


def list_block(items: Iterable[str], *, options: OutputOptions) -> None:
    for item in items:
        print(f"  - {item}", file=options.stream)


@contextmanager
def status(text: str, *, options: OutputOptions) -> Iterator[None]:
    info(f"→ {text}...", options=options)
    try:
        yield
    except Exception:
        error(f"✖ {text}", options=options)
        raise
    else:
        success(f"✔ {text}", options=options)


def prompt(text: str, *, options: OutputOptions, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    options.stream.write(apply_color(f"{text}{suffix}: ", "bold", options=options))
    options.stream.flush()
    user_input = sys.stdin.readline().strip()
    if not user_input and default is not None:
        return default
    return user_input


def confirm(text: str, *, options: OutputOptions, default: bool = True) -> bool:
    default_str = "Y/n" if default else "y/N"
    while True:
        answer = prompt(
            f"{text} ({default_str})", options=options, default="y" if default else "n"
        )
        if answer.lower() in {"y", "yes"}:
            return True
        if answer.lower() in {"n", "no"}:
            return False
        warning("Please answer 'y' or 'n'.", options=options)
