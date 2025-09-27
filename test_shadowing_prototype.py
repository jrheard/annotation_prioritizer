"""Test file demonstrating the shadowing bug from issue #31.

This file contains various shadowing scenarios to validate that our
position-aware resolution correctly handles Python's shadowing semantics.
"""

from math import sqrt

# Call 1: Should resolve to imported sqrt (unresolvable for single-file analysis)
sqrt(16)


# Define local sqrt that shadows the import
def sqrt(x):
    """Local sqrt."""
    return x**0.5


# Call 2: Should resolve to local sqrt at line 13
sqrt(25)

from collections import Counter

Counter()  # Should be unresolvable (import)


class Counter:
    """Local Counter."""

    def __init__(self):
        self.count = 0


Counter()  # Should resolve to local Counter.__init__

from collections import Counter  # Re-import overwrites local

Counter()  # Should be unresolvable again (import)


# Additional test case: function shadowing in nested scopes
def outer():
    sqrt(36)  # Should resolve to module-level sqrt function (line 13)

    def sqrt(x):  # Shadows module-level sqrt within outer()
        return x**0.5 + 1

    sqrt(49)  # Should resolve to outer.sqrt (line 37)


# More complex case: class method shadowing
class Calculator:
    def compute(self, x):
        return x * 2


calc = Calculator()
calc.compute(10)  # Should resolve to Calculator.compute (if we tracked variables)


# Function reference reassignment
def process_data(x):
    return x * 2


process_data(10)  # Should count: 1 call to our function

# Note: In a full implementation, reassigning to an import would make
# subsequent calls unresolvable, but we're not tracking variables in the prototype
