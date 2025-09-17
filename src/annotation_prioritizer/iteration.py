"""Iteration utilities."""

from collections.abc import Callable, Iterable


def first[T](iterable: Iterable[T], predicate: Callable[[T], bool]) -> T | None:
    """Return the first item in iterable that satisfies the predicate, or None if no match.

    Args:
        iterable: The iterable to search through
        predicate: A function that returns True for the desired item

    Returns:
        The first matching item, or None if no item matches

    Examples:
        >>> first([1, 2, 3, 4], lambda x: x > 2)
        3
        >>> first([1, 2, 3, 4], lambda x: x > 10)
        None
    """
    for item in iterable:
        if predicate(item):
            return item
    return None
