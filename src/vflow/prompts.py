from __future__ import annotations

import sys

import typer


def stdin_is_tty() -> bool:
    """Whether someone is at the keyboard to answer a question on this run."""
    stream = getattr(sys, "stdin", None)
    if stream is None:
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def missing_answer(decision: str, flags: str) -> typer.Exit:
    """Refuse to guess an unanswerable question, naming the flags that answer it."""
    typer.echo(f"{decision} Pass {flags}.", err=True)
    return typer.Exit(code=1)


def confirm(question: str, decision: str, flags: str) -> bool:
    """Ask a yes/no question of the person at the terminal, or name the flag instead.

    The answer is never assumed: without a terminal the command stops and says which
    flag carries the decision, so nothing mutating happens on a guess.
    """
    if not stdin_is_tty():
        raise missing_answer(decision, flags)
    return typer.confirm(question, default=False)
