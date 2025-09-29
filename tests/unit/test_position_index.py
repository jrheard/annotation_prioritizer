"""Tests for position-aware name resolution.

Tests verify position-aware name resolution with binary search,
including shadowing scenarios, scope chain resolution, and edge cases.
"""

from annotation_prioritizer.models import (
    NameBinding,
    NameBindingKind,
    PositionIndex,
    QualifiedName,
    Scope,
    ScopeKind,
    ScopeStack,
    make_qualified_name,
)
from annotation_prioritizer.position_index import resolve_name
from annotation_prioritizer.scope_tracker import scope_stack_to_qualified_name


def create_binding(
    name: str,
    line_number: int,
    kind: NameBindingKind,
    scope_stack: ScopeStack,
    qualified_name: QualifiedName | None = None,
) -> NameBinding:
    """Create a NameBinding for testing."""
    return NameBinding(
        name=name,
        line_number=line_number,
        kind=kind,
        qualified_name=qualified_name,
        scope_stack=scope_stack,
        source_module=None,
        target_class=None,
    )


def build_index(bindings: list[NameBinding]) -> PositionIndex:
    """Build a PositionIndex from a list of bindings."""
    index: dict[QualifiedName, dict[str, list[tuple[int, NameBinding]]]] = {}

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
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
        binding = create_binding(
            "sqrt",
            5,
            NameBindingKind.IMPORT,
            module_scope,
        )
        index = build_index([binding])

        # Should resolve at line 10 (after binding)
        result = resolve_name(index, "sqrt", 10, module_scope)
        assert result == binding

    def test_resolve_returns_none_for_unknown_name(self) -> None:
        """Return None when name is not in index."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
        binding = create_binding(
            "sqrt",
            5,
            NameBindingKind.IMPORT,
            module_scope,
        )
        index = build_index([binding])

        result = resolve_name(index, "cos", 10, module_scope)
        assert result is None

    def test_resolve_returns_none_before_binding(self) -> None:
        """Return None when querying before any binding."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
        binding = create_binding(
            "sqrt",
            10,
            NameBindingKind.IMPORT,
            module_scope,
        )
        index = build_index([binding])

        # Query at line 5 (before binding at line 10)
        result = resolve_name(index, "sqrt", 5, module_scope)
        assert result is None

    def test_resolve_at_exact_binding_line(self) -> None:
        """Return None when querying at the exact line of binding."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
        binding = create_binding(
            "sqrt",
            10,
            NameBindingKind.IMPORT,
            module_scope,
        )
        index = build_index([binding])

        # Query at exact line 10 (binding itself)
        # Should return None because we want bindings BEFORE this line
        result = resolve_name(index, "sqrt", 10, module_scope)
        assert result is None


class TestPositionIndexShadowing:
    """Tests for shadowing scenarios where names are redefined."""

    def test_shadowing_two_bindings_same_name(self) -> None:
        """Resolve correct binding when name is shadowed."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

        # Import sqrt at line 5
        import_binding = create_binding(
            "sqrt",
            5,
            NameBindingKind.IMPORT,
            module_scope,
        )

        # Define local sqrt function at line 10
        function_binding = create_binding(
            "sqrt",
            10,
            NameBindingKind.FUNCTION,
            module_scope,
            make_qualified_name("__module__.sqrt"),
        )

        index = build_index([import_binding, function_binding])

        # At line 8, should resolve to import (line 5)
        result = resolve_name(index, "sqrt", 8, module_scope)
        assert result == import_binding

        # At line 15, should resolve to function (line 10)
        result = resolve_name(index, "sqrt", 15, module_scope)
        assert result == function_binding

    def test_shadowing_three_bindings_same_name(self) -> None:
        """Resolve correct binding with multiple shadows."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

        binding_5 = create_binding("x", 5, NameBindingKind.IMPORT, module_scope)
        binding_10 = create_binding(
            "x",
            10,
            NameBindingKind.FUNCTION,
            module_scope,
            make_qualified_name("__module__.x"),
        )
        binding_15 = create_binding(
            "x",
            15,
            NameBindingKind.CLASS,
            module_scope,
            make_qualified_name("__module__.x"),
        )

        index = build_index([binding_5, binding_10, binding_15])

        # Test resolution at different points
        assert resolve_name(index, "x", 7, module_scope) == binding_5
        assert resolve_name(index, "x", 12, module_scope) == binding_10
        assert resolve_name(index, "x", 20, module_scope) == binding_15

    def test_shadowing_reverse_order_insertion(self) -> None:
        """Binary search works regardless of insertion order."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

        # Insert in reverse order (should be sorted internally)
        binding_15 = create_binding("x", 15, NameBindingKind.IMPORT, module_scope)
        binding_10 = create_binding("x", 10, NameBindingKind.IMPORT, module_scope)
        binding_5 = create_binding("x", 5, NameBindingKind.IMPORT, module_scope)

        index = build_index([binding_15, binding_10, binding_5])

        # Should still resolve correctly
        assert resolve_name(index, "x", 7, module_scope) == binding_5
        assert resolve_name(index, "x", 12, module_scope) == binding_10
        assert resolve_name(index, "x", 20, module_scope) == binding_15


class TestPositionIndexScopeChain:
    """Tests for scope chain resolution (inner to outer)."""

    def test_resolve_in_nested_function_scope(self) -> None:
        """Resolve name in nested function scope."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
        function_scope = (
            Scope(ScopeKind.MODULE, "__module__"),
            Scope(ScopeKind.FUNCTION, "foo"),
        )

        # Module-level binding
        module_binding = create_binding(
            "x",
            5,
            NameBindingKind.IMPORT,
            module_scope,
        )

        # Function-level binding (shadows module)
        function_binding = create_binding(
            "x",
            10,
            NameBindingKind.VARIABLE,
            function_scope,
            make_qualified_name("__module__.foo.x"),
        )

        index = build_index([module_binding, function_binding])

        # In module scope at line 20, should resolve to module binding
        result = resolve_name(index, "x", 20, module_scope)
        assert result == module_binding

        # In function scope at line 15, should resolve to function binding
        result = resolve_name(index, "x", 15, function_scope)
        assert result == function_binding

    def test_resolve_falls_back_to_outer_scope(self) -> None:
        """Fall back to outer scope when name not in inner scope."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
        function_scope = (
            Scope(ScopeKind.MODULE, "__module__"),
            Scope(ScopeKind.FUNCTION, "foo"),
        )

        # Only module-level binding
        module_binding = create_binding(
            "sqrt",
            5,
            NameBindingKind.IMPORT,
            module_scope,
        )

        index = build_index([module_binding])

        # In function scope, should fall back to module scope
        result = resolve_name(index, "sqrt", 15, function_scope)
        assert result == module_binding

    def test_inner_scope_shadows_outer_scope(self) -> None:
        """Inner scope binding shadows outer scope binding."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
        class_scope = (
            Scope(ScopeKind.MODULE, "__module__"),
            Scope(ScopeKind.CLASS, "Calculator"),
        )

        # Module-level sqrt at line 5
        module_binding = create_binding(
            "sqrt",
            5,
            NameBindingKind.IMPORT,
            module_scope,
        )

        # Class-level sqrt at line 10
        class_binding = create_binding(
            "sqrt",
            10,
            NameBindingKind.FUNCTION,
            class_scope,
            make_qualified_name("__module__.Calculator.sqrt"),
        )

        index = build_index([module_binding, class_binding])

        # In class scope at line 15, should resolve to class binding
        result = resolve_name(index, "sqrt", 15, class_scope)
        assert result == class_binding

        # In module scope at line 15, should resolve to module binding
        result = resolve_name(index, "sqrt", 15, module_scope)
        assert result == module_binding


class TestPositionIndexEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_index(self) -> None:
        """Resolve returns None for empty index."""
        index = build_index([])
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

        result = resolve_name(index, "sqrt", 10, module_scope)
        assert result is None

    def test_empty_scope_stack(self) -> None:
        """Handle empty scope stack (treats as module scope)."""
        empty_scope: ScopeStack = ()
        binding = create_binding(
            "x",
            5,
            NameBindingKind.IMPORT,
            (Scope(ScopeKind.MODULE, "__module__"),),
        )
        index = build_index([binding])

        # Empty scope should be treated as module scope
        result = resolve_name(index, "x", 10, empty_scope)
        assert result == binding

    def test_single_scope_in_stack(self) -> None:
        """Handle scope stack with only module scope."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
        binding = create_binding(
            "x",
            5,
            NameBindingKind.IMPORT,
            module_scope,
        )
        index = build_index([binding])

        result = resolve_name(index, "x", 10, module_scope)
        assert result == binding

    def test_deeply_nested_scope(self) -> None:
        """Resolve in deeply nested scope."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
        deeply_nested_scope = (
            Scope(ScopeKind.MODULE, "__module__"),
            Scope(ScopeKind.CLASS, "Outer"),
            Scope(ScopeKind.CLASS, "Inner"),
            Scope(ScopeKind.FUNCTION, "method"),
        )

        module_binding = create_binding(
            "x",
            5,
            NameBindingKind.IMPORT,
            module_scope,
        )

        index = build_index([module_binding])

        # Should find binding from module scope even in deeply nested scope
        result = resolve_name(index, "x", 50, deeply_nested_scope)
        assert result == module_binding

    def test_multiple_names_same_scope(self) -> None:
        """Resolve different names in the same scope."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

        sqrt_binding = create_binding("sqrt", 5, NameBindingKind.IMPORT, module_scope)
        cos_binding = create_binding("cos", 7, NameBindingKind.IMPORT, module_scope)
        sin_binding = create_binding("sin", 9, NameBindingKind.IMPORT, module_scope)

        index = build_index([sqrt_binding, cos_binding, sin_binding])

        # Each name should resolve independently
        assert resolve_name(index, "sqrt", 10, module_scope) == sqrt_binding
        assert resolve_name(index, "cos", 10, module_scope) == cos_binding
        assert resolve_name(index, "sin", 10, module_scope) == sin_binding


class TestPositionIndexBinarySearchEfficiency:
    """Tests verifying binary search finds correct binding efficiently."""

    def test_binary_search_with_many_bindings(self) -> None:
        """Binary search works correctly with many bindings."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

        # Create many bindings for the same name
        bindings = [
            create_binding("x", line, NameBindingKind.VARIABLE, module_scope)
            for line in range(10, 110, 10)  # Lines 10, 20, 30, ..., 100
        ]

        index = build_index(bindings)

        # Test resolution at various points
        assert resolve_name(index, "x", 15, module_scope) == bindings[0]  # Line 10
        assert resolve_name(index, "x", 35, module_scope) == bindings[2]  # Line 30
        assert resolve_name(index, "x", 55, module_scope) == bindings[4]  # Line 50
        assert resolve_name(index, "x", 95, module_scope) == bindings[8]  # Line 90
        assert resolve_name(index, "x", 105, module_scope) == bindings[9]  # Line 100

    def test_binary_search_boundary_conditions(self) -> None:
        """Binary search handles boundary conditions correctly."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

        binding_10 = create_binding("x", 10, NameBindingKind.VARIABLE, module_scope)
        binding_20 = create_binding("x", 20, NameBindingKind.VARIABLE, module_scope)

        index = build_index([binding_10, binding_20])

        # Just before first binding
        assert resolve_name(index, "x", 9, module_scope) is None

        # Just after first binding
        assert resolve_name(index, "x", 11, module_scope) == binding_10

        # Just before second binding
        assert resolve_name(index, "x", 19, module_scope) == binding_10

        # Just after second binding
        assert resolve_name(index, "x", 21, module_scope) == binding_20


class TestPositionIndexIssueShadowingScenarios:
    """Tests for shadowing scenarios from issue #31."""

    def test_import_shadowed_by_local_function(self) -> None:
        """Test case from issue #31: import shadowed by local function."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

        # from math import sqrt (line 1)
        import_sqrt = create_binding("sqrt", 1, NameBindingKind.IMPORT, module_scope)

        # def sqrt(): ... (line 10)
        function_sqrt = create_binding(
            "sqrt",
            10,
            NameBindingKind.FUNCTION,
            module_scope,
            make_qualified_name("__module__.sqrt"),
        )

        index = build_index([import_sqrt, function_sqrt])

        # Before shadowing: sqrt() at line 5 should resolve to import
        result = resolve_name(index, "sqrt", 5, module_scope)
        assert result == import_sqrt
        assert result is not None
        assert result.kind == NameBindingKind.IMPORT

        # After shadowing: sqrt() at line 15 should resolve to local function
        result = resolve_name(index, "sqrt", 15, module_scope)
        assert result == function_sqrt
        assert result is not None
        assert result.kind == NameBindingKind.FUNCTION

    def test_local_function_shadowed_by_later_import(self) -> None:
        """Local function shadowed by later import (unusual but valid Python)."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

        # def sqrt(): ... (line 5)
        function_sqrt = create_binding(
            "sqrt",
            5,
            NameBindingKind.FUNCTION,
            module_scope,
            make_qualified_name("__module__.sqrt"),
        )

        # from math import sqrt (line 15) - shadows the function
        import_sqrt = create_binding("sqrt", 15, NameBindingKind.IMPORT, module_scope)

        index = build_index([function_sqrt, import_sqrt])

        # Before import: sqrt() at line 10 resolves to local function
        result = resolve_name(index, "sqrt", 10, module_scope)
        assert result == function_sqrt
        assert result is not None
        assert result.kind == NameBindingKind.FUNCTION

        # After import: sqrt() at line 20 resolves to import
        result = resolve_name(index, "sqrt", 20, module_scope)
        assert result == import_sqrt
        assert result is not None
        assert result.kind == NameBindingKind.IMPORT

    def test_class_shadowing_import(self) -> None:
        """Class definition shadows imported name."""
        module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

        # from typing import List (line 1)
        import_list = create_binding("List", 1, NameBindingKind.IMPORT, module_scope)

        # class List: ... (line 10)
        class_list = create_binding(
            "List",
            10,
            NameBindingKind.CLASS,
            module_scope,
            make_qualified_name("__module__.List"),
        )

        index = build_index([import_list, class_list])

        # Before class: List at line 5 resolves to import
        result = resolve_name(index, "List", 5, module_scope)
        assert result == import_list

        # After class: List at line 15 resolves to class
        result = resolve_name(index, "List", 15, module_scope)
        assert result == class_list
