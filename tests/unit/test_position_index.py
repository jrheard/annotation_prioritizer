"""Tests for position-aware name resolution.

Tests verify position-aware name resolution with binary search,
including shadowing scenarios, scope chain resolution, and edge cases.
Tests also cover the build_position_index() factory function for
creating indexes from collected name bindings.
"""

import pytest

from annotation_prioritizer.models import (
    NameBinding,
    QualifiedName,
    Scope,
    ScopeKind,
    ScopeStack,
    make_qualified_name,
)
from annotation_prioritizer.position_index import (
    LineBinding,
    PositionIndex,
    build_position_index,
    resolve_name,
)
from annotation_prioritizer.scope_tracker import scope_stack_to_qualified_name
from tests.helpers.factories import (
    make_class_binding,
    make_class_scope,
    make_function_binding,
    make_function_scope,
    make_import_binding,
    make_module_scope,
    make_variable_binding,
)


def build_index(bindings: list[NameBinding]) -> PositionIndex:
    """Build a PositionIndex from a list of bindings."""
    index: dict[QualifiedName, dict[str, list[LineBinding]]] = {}

    for binding in bindings:
        scope_name = scope_stack_to_qualified_name(binding.scope_stack)

        if scope_name not in index:
            index[scope_name] = {}

        if binding.name not in index[scope_name]:
            index[scope_name][binding.name] = []

        index[scope_name][binding.name].append((binding.line_number, binding))

    # Sort each name's bindings by line number for binary search
    for scope_dict in index.values():
        for binding_list in scope_dict.values():
            binding_list.sort(key=lambda x: x[0])

    return index


class TestPositionIndexBasicResolution:
    """Tests for basic name resolution functionality."""

    def test_resolve_single_binding(self) -> None:
        """Resolve a name with a single binding."""
        binding = make_import_binding("sqrt", "math", line_number=5)
        index = build_index([binding])

        # Should resolve at line 10 (after binding)
        result = resolve_name(index, "sqrt", 10, make_module_scope())
        assert result == binding

    def test_resolve_returns_none_for_unknown_name(self) -> None:
        """Return None when name is not in index."""
        binding = make_import_binding("sqrt", "math", line_number=5)
        index = build_index([binding])

        result = resolve_name(index, "cos", 10, make_module_scope())
        assert result is None

    def test_resolve_returns_none_before_binding(self) -> None:
        """Return None when querying before any binding."""
        binding = make_import_binding("sqrt", "math", line_number=10)
        index = build_index([binding])

        # Query at line 5 (before binding at line 10)
        result = resolve_name(index, "sqrt", 5, make_module_scope())
        assert result is None

    def test_resolve_at_exact_binding_line(self) -> None:
        """Return None when querying at the exact line of binding."""
        binding = make_import_binding("sqrt", "math", line_number=10)
        index = build_index([binding])

        # Query at exact line 10 (binding itself)
        # Should return None because we want bindings BEFORE this line
        result = resolve_name(index, "sqrt", 10, make_module_scope())
        assert result is None


class TestPositionIndexShadowing:
    """Tests for shadowing scenarios where names are redefined."""

    def test_shadowing_two_bindings_same_name(self) -> None:
        """Resolve correct binding when name is shadowed."""
        # Import sqrt at line 5
        import_binding = make_import_binding("sqrt", "math", line_number=5)

        # Define local sqrt function at line 10
        function_binding = make_function_binding("sqrt", line_number=10)

        index = build_index([import_binding, function_binding])

        # At line 8, should resolve to import (line 5)
        result = resolve_name(index, "sqrt", 8, make_module_scope())
        assert result == import_binding

        # At line 15, should resolve to function (line 10)
        result = resolve_name(index, "sqrt", 15, make_module_scope())
        assert result == function_binding

    def test_shadowing_three_bindings_same_name(self) -> None:
        """Resolve correct binding with multiple shadows."""
        binding_5 = make_import_binding("x", "foo", line_number=5)
        binding_10 = make_function_binding("x", line_number=10)
        binding_15 = make_class_binding("x", line_number=15)

        index = build_index([binding_5, binding_10, binding_15])

        # Test resolution at different points
        assert resolve_name(index, "x", 7, make_module_scope()) == binding_5
        assert resolve_name(index, "x", 12, make_module_scope()) == binding_10
        assert resolve_name(index, "x", 20, make_module_scope()) == binding_15

    def test_shadowing_reverse_order_insertion(self) -> None:
        """Binary search works regardless of insertion order."""
        # Insert in reverse order (should be sorted internally)
        binding_15 = make_import_binding("x", "foo", line_number=15)
        binding_10 = make_import_binding("x", "bar", line_number=10)
        binding_5 = make_import_binding("x", "baz", line_number=5)

        index = build_index([binding_15, binding_10, binding_5])

        # Should still resolve correctly
        assert resolve_name(index, "x", 7, make_module_scope()) == binding_5
        assert resolve_name(index, "x", 12, make_module_scope()) == binding_10
        assert resolve_name(index, "x", 20, make_module_scope()) == binding_15


class TestPositionIndexScopeChain:
    """Tests for scope chain resolution (inner to outer)."""

    def test_resolve_in_nested_function_scope(self) -> None:
        """Resolve name in nested function scope."""
        function_scope = make_function_scope("foo")

        # Module-level binding
        module_binding = make_import_binding("x", "bar", line_number=5)

        # Function-level binding (shadows module)
        function_binding = make_variable_binding(
            "x",
            line_number=10,
            scope_stack=function_scope,
            qualified_name=make_qualified_name("__module__.foo.x"),
        )

        index = build_index([module_binding, function_binding])

        # In module scope at line 20, should resolve to module binding
        result = resolve_name(index, "x", 20, make_module_scope())
        assert result == module_binding

        # In function scope at line 15, should resolve to function binding
        result = resolve_name(index, "x", 15, function_scope)
        assert result == function_binding

    def test_resolve_falls_back_to_outer_scope(self) -> None:
        """Fall back to outer scope when name not in inner scope."""
        function_scope = make_function_scope("foo")

        # Only module-level binding
        module_binding = make_import_binding("sqrt", "math", line_number=5)

        index = build_index([module_binding])

        # In function scope, should fall back to module scope
        result = resolve_name(index, "sqrt", 15, function_scope)
        assert result == module_binding

    def test_inner_scope_shadows_outer_scope(self) -> None:
        """Inner scope binding shadows outer scope binding."""
        class_scope = make_class_scope("Calculator")

        # Module-level sqrt at line 5
        module_binding = make_import_binding("sqrt", "math", line_number=5)

        # Class-level sqrt at line 10
        class_binding = make_function_binding(
            "sqrt",
            line_number=10,
            scope_stack=class_scope,
            qualified_name=make_qualified_name("__module__.Calculator.sqrt"),
        )

        index = build_index([module_binding, class_binding])

        # In class scope at line 15, should resolve to class binding
        result = resolve_name(index, "sqrt", 15, class_scope)
        assert result == class_binding

        # In module scope at line 15, should resolve to module binding
        result = resolve_name(index, "sqrt", 15, make_module_scope())
        assert result == module_binding


class TestPositionIndexEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_index(self) -> None:
        """Resolve returns None for empty index."""
        index = build_index([])

        result = resolve_name(index, "sqrt", 10, make_module_scope())
        assert result is None

    def test_empty_scope_stack_raises_error(self) -> None:
        """resolve_name raises ValueError for empty scope stack."""
        empty_scope: ScopeStack = ()
        binding = make_import_binding("x", "foo", line_number=5)
        index = build_index([binding])

        with pytest.raises(ValueError, match="scope_stack must not be empty"):
            resolve_name(index, "x", 10, empty_scope)

    def test_single_scope_in_stack(self) -> None:
        """Handle scope stack with only module scope."""
        binding = make_import_binding("x", "foo", line_number=5)
        index = build_index([binding])

        result = resolve_name(index, "x", 10, make_module_scope())
        assert result == binding

    def test_deeply_nested_scope(self) -> None:
        """Resolve in deeply nested scope."""
        deeply_nested_scope = (
            Scope(ScopeKind.MODULE, "__module__"),
            Scope(ScopeKind.CLASS, "Outer"),
            Scope(ScopeKind.CLASS, "Inner"),
            Scope(ScopeKind.FUNCTION, "method"),
        )

        module_binding = make_import_binding("x", "foo", line_number=5)

        index = build_index([module_binding])

        # Should find binding from module scope even in deeply nested scope
        result = resolve_name(index, "x", 50, deeply_nested_scope)
        assert result == module_binding

    def test_multiple_names_same_scope(self) -> None:
        """Resolve different names in the same scope."""
        sqrt_binding = make_import_binding("sqrt", "math", line_number=5)
        cos_binding = make_import_binding("cos", "math", line_number=7)
        sin_binding = make_import_binding("sin", "math", line_number=9)

        index = build_index([sqrt_binding, cos_binding, sin_binding])

        # Each name should resolve independently
        assert resolve_name(index, "sqrt", 10, make_module_scope()) == sqrt_binding
        assert resolve_name(index, "cos", 10, make_module_scope()) == cos_binding
        assert resolve_name(index, "sin", 10, make_module_scope()) == sin_binding


class TestPositionIndexBinarySearchEfficiency:
    """Tests verifying binary search finds correct binding efficiently."""

    def test_binary_search_with_many_bindings(self) -> None:
        """Binary search works correctly with many bindings."""
        # Create many bindings for the same name
        # Lines 10, 20, 30, ..., 100
        bindings = [make_variable_binding("x", line_number=line) for line in range(10, 110, 10)]

        index = build_index(bindings)

        # Test resolution at various points
        assert resolve_name(index, "x", 15, make_module_scope()) == bindings[0]  # Line 10
        assert resolve_name(index, "x", 35, make_module_scope()) == bindings[2]  # Line 30
        assert resolve_name(index, "x", 55, make_module_scope()) == bindings[4]  # Line 50
        assert resolve_name(index, "x", 95, make_module_scope()) == bindings[8]  # Line 90
        assert resolve_name(index, "x", 105, make_module_scope()) == bindings[9]  # Line 100

    def test_binary_search_boundary_conditions(self) -> None:
        """Binary search handles boundary conditions correctly."""
        binding_10 = make_variable_binding("x", line_number=10)
        binding_20 = make_variable_binding("x", line_number=20)

        index = build_index([binding_10, binding_20])

        # Just before first binding
        assert resolve_name(index, "x", 9, make_module_scope()) is None

        # Just after first binding
        assert resolve_name(index, "x", 11, make_module_scope()) == binding_10

        # Just before second binding
        assert resolve_name(index, "x", 19, make_module_scope()) == binding_10

        # Just after second binding
        assert resolve_name(index, "x", 21, make_module_scope()) == binding_20


class TestPositionIndexIssueShadowingScenarios:
    """Tests for shadowing scenarios from issue #31."""

    def test_import_shadowed_by_local_function(self) -> None:
        """Test case from issue #31: import shadowed by local function."""
        # from math import sqrt (line 1)
        import_sqrt = make_import_binding("sqrt", "math")

        # def sqrt(): ... (line 10)
        function_sqrt = make_function_binding("sqrt", line_number=10)

        index = build_index([import_sqrt, function_sqrt])

        # Before shadowing: sqrt() at line 5 should resolve to import
        result = resolve_name(index, "sqrt", 5, make_module_scope())
        assert result == import_sqrt
        assert result is not None

        # After shadowing: sqrt() at line 15 should resolve to local function
        result = resolve_name(index, "sqrt", 15, make_module_scope())
        assert result == function_sqrt
        assert result is not None

    def test_local_function_shadowed_by_later_import(self) -> None:
        """Local function shadowed by later import (unusual but valid Python)."""
        # def sqrt(): ... (line 5)
        function_sqrt = make_function_binding("sqrt", line_number=5)

        # from math import sqrt (line 15) - shadows the function
        import_sqrt = make_import_binding("sqrt", "math", line_number=15)

        index = build_index([function_sqrt, import_sqrt])

        # Before import: sqrt() at line 10 resolves to local function
        result = resolve_name(index, "sqrt", 10, make_module_scope())
        assert result == function_sqrt
        assert result is not None

        # After import: sqrt() at line 20 resolves to import
        result = resolve_name(index, "sqrt", 20, make_module_scope())
        assert result == import_sqrt
        assert result is not None

    def test_class_shadowing_import(self) -> None:
        """Class definition shadows imported name."""
        # from typing import List (line 1)
        import_list = make_import_binding("List", "typing")

        # class List: ... (line 10)
        class_list = make_class_binding("List", line_number=10)

        index = build_index([import_list, class_list])

        # Before class: List at line 5 resolves to import
        result = resolve_name(index, "List", 5, make_module_scope())
        assert result == import_list

        # After class: List at line 15 resolves to class
        result = resolve_name(index, "List", 15, make_module_scope())
        assert result == class_list


class TestBuildPositionIndex:
    """Tests for build_position_index() factory function."""

    def test_build_index_with_no_bindings(self) -> None:
        """Empty bindings list should create empty index."""
        index = build_position_index([])

        # Should resolve to None for any name
        result = resolve_name(index, "foo", 10, make_module_scope())
        assert result is None

    def test_build_index_with_single_binding(self) -> None:
        """Index with single binding should be resolvable."""
        binding = make_import_binding("sqrt", "math")
        index = build_position_index([binding])

        # Should resolve sqrt after line 1
        result = resolve_name(index, "sqrt", 10, make_module_scope())
        assert result == binding

        # Should not resolve before line 1
        result = resolve_name(index, "sqrt", 1, make_module_scope())
        assert result is None

    def test_build_index_sorts_bindings_by_line_number(self) -> None:
        """Bindings should be sorted by line number for correct resolution."""
        # Create bindings out of order
        binding2 = make_function_binding("foo", line_number=20)
        binding1 = make_import_binding("foo", "bar", line_number=10)

        # Build index with out-of-order bindings
        index = build_position_index([binding2, binding1])

        # At line 15, should resolve to the import (line 10)
        result = resolve_name(index, "foo", 15, make_module_scope())
        assert result == binding1

        # At line 25, should resolve to the function (line 20)
        result = resolve_name(index, "foo", 25, make_module_scope())
        assert result == binding2

    def test_build_index_resolves_variable_to_class(self) -> None:
        """Variables referencing classes should have target_class resolved."""
        class_binding = make_class_binding("Calculator")
        var_binding = make_variable_binding("calc", line_number=10)

        # Build index with unresolved variable
        index = build_position_index([class_binding, var_binding], [(var_binding, "Calculator")])

        # The variable should now have target_class resolved
        result = resolve_name(index, "calc", 15, make_module_scope())
        assert result is not None
        assert result.target_class == make_qualified_name("__module__.Calculator")

    def test_build_index_variable_resolves_to_shadowed_class(self) -> None:
        """Variable resolution should respect shadowing (issue #31)."""
        # Import Calculator from module
        import_binding = make_import_binding("Calculator", "external")

        # Local Calculator class shadows the import
        class_binding = make_class_binding("Calculator", line_number=10)

        # Variable created after the local class
        var_binding = make_variable_binding("calc", line_number=20)

        index = build_position_index(
            [import_binding, class_binding, var_binding], [(var_binding, "Calculator")]
        )

        # Variable should resolve to the LOCAL class, not the import
        result = resolve_name(index, "calc", 25, make_module_scope())
        assert result is not None
        assert result.target_class == make_qualified_name("__module__.Calculator")

    def test_build_index_unresolvable_variable_keeps_none(self) -> None:
        """Variables that can't be resolved should keep target_class=None."""
        var_binding = make_variable_binding("calc", line_number=10)

        # Try to resolve to a class that doesn't exist
        index = build_position_index([var_binding], [(var_binding, "NonexistentClass")])

        result = resolve_name(index, "calc", 15, make_module_scope())
        assert result is not None
        assert result.target_class is None

    def test_build_index_variable_wont_resolve_to_function(self) -> None:
        """Variables referencing functions should not get target_class set."""
        func_binding = make_function_binding("process")
        var_binding = make_variable_binding("p", line_number=10)

        # Variable references a function, not a class
        index = build_position_index([func_binding, var_binding], [(var_binding, "process")])

        result = resolve_name(index, "p", 15, make_module_scope())
        assert result is not None
        assert result.target_class is None  # Should not resolve to function

    def test_build_index_variable_wont_resolve_to_import(self) -> None:
        """Variables referencing imports should not get target_class set."""
        import_binding = make_import_binding("math", "math")
        var_binding = make_variable_binding("m", line_number=10)

        # Variable references an import, not a class
        index = build_position_index([import_binding, var_binding], [(var_binding, "math")])

        result = resolve_name(index, "m", 15, make_module_scope())
        assert result is not None
        assert result.target_class is None  # Should not resolve to import

    def test_build_index_shadowing_import_by_function(self) -> None:
        """Import shadowed by function (issue #31 scenario)."""
        # Import: from math import sqrt
        import_binding = make_import_binding("sqrt", "math")

        # Function: def sqrt(): ...
        func_binding = make_function_binding("sqrt", line_number=10)

        index = build_position_index([import_binding, func_binding])

        # Before function definition: should resolve to import
        result = resolve_name(index, "sqrt", 5, make_module_scope())
        assert result == import_binding

        # After function definition: should resolve to function
        result = resolve_name(index, "sqrt", 15, make_module_scope())
        assert result == func_binding

    def test_build_index_shadowing_function_by_import(self) -> None:
        """Function shadowed by later import (issue #31 scenario)."""
        # Function: def sqrt(): ...
        func_binding = make_function_binding("sqrt")

        # Import: from math import sqrt
        import_binding = make_import_binding("sqrt", "math", line_number=10)

        index = build_position_index([func_binding, import_binding])

        # Before import: should resolve to function
        result = resolve_name(index, "sqrt", 5, make_module_scope())
        assert result == func_binding

        # After import: should resolve to import
        result = resolve_name(index, "sqrt", 15, make_module_scope())
        assert result == import_binding

    def test_build_index_variable_reassignment(self) -> None:
        """Multiple assignments to same variable should be tracked."""
        class1_binding = make_class_binding("Calculator")
        class2_binding = make_class_binding("AdvancedCalculator", line_number=5)

        # First assignment to calc variable
        var1_binding = make_variable_binding("calc", line_number=10)

        # Second assignment to calc variable (reassignment)
        var2_binding = make_variable_binding("calc", line_number=20)

        index = build_position_index(
            [class1_binding, class2_binding, var1_binding, var2_binding],
            [(var1_binding, "Calculator"), (var2_binding, "AdvancedCalculator")],
        )

        # At line 15: should resolve to first assignment
        result = resolve_name(index, "calc", 15, make_module_scope())
        assert result is not None
        assert result.line_number == 10
        assert result.target_class == make_qualified_name("__module__.Calculator")

        # At line 25: should resolve to second assignment
        result = resolve_name(index, "calc", 25, make_module_scope())
        assert result is not None
        assert result.line_number == 20
        assert result.target_class == make_qualified_name("__module__.AdvancedCalculator")

    def test_build_index_multiple_shadows_in_scope(self) -> None:
        """Multiple shadowing events for the same name (issue #31)."""
        # from math import sqrt (line 1)
        import1 = make_import_binding("sqrt", "math")

        # def sqrt(): ... (line 10)
        func = make_function_binding("sqrt", line_number=10)

        # from numpy import sqrt (line 20)
        import2 = make_import_binding("sqrt", "numpy", line_number=20)

        index = build_position_index([import1, func, import2])

        # Line 5: should resolve to math.sqrt
        result = resolve_name(index, "sqrt", 5, make_module_scope())
        assert result == import1

        # Line 15: should resolve to local function
        result = resolve_name(index, "sqrt", 15, make_module_scope())
        assert result == func

        # Line 25: should resolve to numpy.sqrt
        result = resolve_name(index, "sqrt", 25, make_module_scope())
        assert result == import2

    def test_build_index_class_shadows_import(self) -> None:
        """Class definition shadows import (issue #31 scenario)."""
        # Import: from external import Calculator
        import_binding = make_import_binding("Calculator", "external")

        # Class: class Calculator: ...
        class_binding = make_class_binding("Calculator", line_number=10)

        index = build_position_index([import_binding, class_binding])

        # Before class: resolves to import
        result = resolve_name(index, "Calculator", 5, make_module_scope())
        assert result == import_binding

        # After class: resolves to local class
        result = resolve_name(index, "Calculator", 15, make_module_scope())
        assert result == class_binding

    def test_build_index_variables_in_nested_scope(self) -> None:
        """Variable resolution works in nested scopes."""
        func_scope = make_function_scope("process")

        # class Calculator at module level
        class_binding = make_class_binding("Calculator")

        # calc = Calculator() inside function
        var_binding = make_variable_binding(
            "calc",
            line_number=10,
            scope_stack=func_scope,
            qualified_name=make_qualified_name("__module__.process.calc"),
        )

        index = build_position_index([class_binding, var_binding], [(var_binding, "Calculator")])

        # Variable in function scope should resolve to module-level class
        result = resolve_name(index, "calc", 15, func_scope)
        assert result is not None
        assert result.target_class == make_qualified_name("__module__.Calculator")

    def test_build_index_with_no_unresolved_variables(self) -> None:
        """Index building works when unresolved_variables is None."""
        binding = make_function_binding("foo")

        # Call with unresolved_variables=None (default)
        index = build_position_index([binding])

        result = resolve_name(index, "foo", 10, make_module_scope())
        assert result == binding

    def test_build_index_with_empty_unresolved_list(self) -> None:
        """Index building works when unresolved_variables is empty list."""
        binding = make_function_binding("foo")

        # Call with empty list
        index = build_position_index([binding], [])

        result = resolve_name(index, "foo", 10, make_module_scope())
        assert result == binding
