"""Unit tests for class instantiation tracking functionality."""

from __future__ import annotations

from annotation_prioritizer.models import make_qualified_name
from tests.helpers.function_parsing import count_calls_from_source, parse_functions_from_source


def test_class_with_explicit_init() -> None:
    """Instantiation of class with explicit __init__ counts correctly."""
    source = """
class Calculator:
    def __init__(self, x: int) -> None:
        self.x = x

# Multiple ways to instantiate
calc1 = Calculator(42)
calc2 = Calculator(x=10)
Calculator(5)  # Direct instantiation without assignment
"""
    counts = count_calls_from_source(source)

    # Verify Calculator.__init__ was called 3 times
    init_name = make_qualified_name("__module__.Calculator.__init__")
    assert counts.get(init_name, 0) == 3


def test_class_without_init() -> None:
    """Instantiation of class without __init__ counts synthetic one."""
    source = """
class SimpleClass:
    pass

# Instantiate class without explicit __init__
obj1 = SimpleClass()
obj2 = SimpleClass()
SimpleClass()  # Direct instantiation
"""
    # Verify synthetic __init__ was created
    functions = parse_functions_from_source(source)
    init_name = make_qualified_name("__module__.SimpleClass.__init__")
    assert any(func.qualified_name == init_name for func in functions)

    # Verify SimpleClass.__init__ was called 3 times
    counts = count_calls_from_source(source)
    assert counts.get(init_name, 0) == 3


def test_multiple_instantiations() -> None:
    """Multiple instantiations are counted."""
    source = """
class Widget:
    def __init__(self) -> None:
        pass

# Multiple instantiations in different contexts
widgets = []
for i in range(5):
    widgets.append(Widget())

# Additional instantiations
w1 = Widget()
w2 = Widget()
"""
    counts = count_calls_from_source(source)

    # Verify Widget.__init__ lexical occurrences
    # Static analysis counts: Widget() once in loop body, w1 = Widget(), w2 = Widget()
    init_name = make_qualified_name("__module__.Widget.__init__")
    assert counts.get(init_name, 0) == 3


def test_instantiation_with_wrong_params() -> None:
    """Instantiations with wrong parameters still count.

    We count all instantiation attempts regardless of validity,
    as our role is annotation prioritization, not type checking.
    """
    source = """
class StrictClass:
    def __init__(self, x: int) -> None:
        self.x = x

# Various instantiation attempts (some invalid)
obj1 = StrictClass(42)  # Valid
obj2 = StrictClass()  # Missing required param - still counts
obj3 = StrictClass(1, 2, 3)  # Too many params - still counts
obj4 = StrictClass("not_int")  # Wrong type - still counts
"""
    counts = count_calls_from_source(source)

    # Verify all instantiation attempts are counted
    init_name = make_qualified_name("__module__.StrictClass.__init__")
    assert counts.get(init_name, 0) == 4


def test_variable_assignment_instantiation() -> None:
    """Calc = Calculator() counts as instantiation."""
    source = """
class Calculator:
    def __init__(self) -> None:
        pass

# Various assignment patterns
calc = Calculator()
self.calc = Calculator()
some_dict = {}
some_dict['calc'] = Calculator()
calcs = [Calculator() for _ in range(3)]
"""
    counts = count_calls_from_source(source)

    # Verify lexical instantiation occurrences
    # Static analysis counts each Calculator() appearance in the source
    init_name = make_qualified_name("__module__.Calculator.__init__")
    assert counts.get(init_name, 0) == 4  # calc, self.calc, dict['calc'], and list comp


def test_direct_instantiation() -> None:
    """Calculator().method() counts instantiation."""
    source = """
class Calculator:
    def __init__(self) -> None:
        self.value = 0

    def add(self, x: int) -> int:
        self.value += x
        return self.value

# Direct instantiation and method call
result = Calculator().add(5)

# Chained calls
Calculator().add(1)
Calculator().add(2)
"""
    counts = count_calls_from_source(source)

    # Verify Calculator.__init__ was called 3 times
    init_name = make_qualified_name("__module__.Calculator.__init__")
    assert counts.get(init_name, 0) == 3

    # Method calls on direct instantiations are not resolved
    # Calculator().add() - the add() call is not tracked as it's on an anonymous instance
    add_name = make_qualified_name("__module__.Calculator.add")
    assert counts.get(add_name, 0) == 0  # Direct instantiation method calls not tracked


def test_nested_class_instantiation() -> None:
    """Test instantiation of nested classes."""
    source = """
class Outer:
    class Inner:
        def __init__(self) -> None:
            pass

# Direct nested instantiation
inner = Outer.Inner()

# Instantiation of outer class
outer = Outer()
"""
    counts = count_calls_from_source(source)

    # Verify Outer.__init__ was counted (synthetic)
    outer_init = make_qualified_name("__module__.Outer.__init__")
    assert counts.get(outer_init, 0) == 1

    # Verify nested class instantiation is tracked
    inner_init = make_qualified_name("__module__.Outer.Inner.__init__")
    assert counts.get(inner_init, 0) == 1


def test_deeply_nested_class_instantiation() -> None:
    """Test instantiation of deeply nested classes."""
    source = """
class Outer:
    class Middle:
        class Inner:
            def __init__(self, value: int) -> None:
                self.value = value

# Deeply nested instantiation
obj = Outer.Middle.Inner(42)
"""
    counts = count_calls_from_source(source)

    # Verify deeply nested class instantiation is tracked
    inner_init = make_qualified_name("__module__.Outer.Middle.Inner.__init__")
    assert counts.get(inner_init, 0) == 1


def test_class_in_function() -> None:
    """Test class defined inside function has correct instantiation tracking."""
    source = """
def create_class():
    class LocalClass:
        def __init__(self, value: int) -> None:
            self.value = value

    # Instantiate local class
    obj1 = LocalClass(1)
    obj2 = LocalClass(2)
    return LocalClass(3)

create_class()
"""
    counts = count_calls_from_source(source)

    # Verify LocalClass.__init__ was called 3 times
    local_init = make_qualified_name("__module__.create_class.LocalClass.__init__")
    assert counts.get(local_init, 0) == 3

    # Verify create_class was called once
    create_func = make_qualified_name("__module__.create_class")
    assert counts.get(create_func, 0) == 1


def test_imported_class_instantiation() -> None:
    """Test that imported class instantiation is not counted (out of scope)."""
    source = """
from datetime import datetime

# These should not be counted as they're imported classes
dt1 = datetime.now()
dt2 = datetime(2024, 1, 1)

# Only local classes should be counted
class LocalClass:
    pass

local = LocalClass()
"""
    counts = count_calls_from_source(source)

    # Only LocalClass.__init__ should be counted
    local_init = make_qualified_name("__module__.LocalClass.__init__")
    assert counts.get(local_init, 0) == 1

    # datetime should not be in our call counts (it's imported, not local)
    datetime_init = make_qualified_name("datetime.__init__")
    assert datetime_init not in counts
