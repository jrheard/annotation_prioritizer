"""Utilities for working with AST function arguments.

This module provides focused utilities for iterating over and extracting
information from ast.arguments nodes, ensuring consistent handling of all
Python parameter types across the codebase.
"""

import ast
from collections.abc import Iterator
from enum import Enum, auto


class ArgumentKind(Enum):
    """Type of function argument."""

    REGULAR = auto()  # Regular positional or keyword argument
    POSITIONAL_ONLY = auto()  # Positional-only argument (before /)
    KEYWORD_ONLY = auto()  # Keyword-only argument (after *)
    VAR_POSITIONAL = auto()  # *args
    VAR_KEYWORD = auto()  # **kwargs


def iter_all_arguments(args: ast.arguments) -> Iterator[tuple[ast.arg, ArgumentKind]]:
    """Iterate over all arguments in an ast.arguments node.

    Processes all parameter types supported by Python: regular positional arguments,
    positional-only arguments (Python 3.8+), keyword-only arguments, *args, and
    **kwargs. Yields all argument types in the order they would appear in a function
    signature, providing both the AST node and the kind of argument.

    Args:
        args: AST arguments node from a function definition

    Yields:
        Tuples of (ast.arg node, ArgumentKind) for each parameter

    Example:
        >>> for arg, kind in iter_all_arguments(func_node.args):
        ...     if arg.annotation:
        ...         process_annotation(arg.arg, arg.annotation)
    """
    # Positional-only arguments (Python 3.8+)
    for arg in args.posonlyargs:
        yield arg, ArgumentKind.POSITIONAL_ONLY

    # Regular positional arguments
    for arg in args.args:
        yield arg, ArgumentKind.REGULAR

    # *args parameter
    if args.vararg is not None:
        yield args.vararg, ArgumentKind.VAR_POSITIONAL

    # Keyword-only arguments
    for arg in args.kwonlyargs:
        yield arg, ArgumentKind.KEYWORD_ONLY

    # **kwargs parameter
    if args.kwarg is not None:
        yield args.kwarg, ArgumentKind.VAR_KEYWORD
