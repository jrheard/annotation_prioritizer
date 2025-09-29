"""Tests for build_position_index() factory function.

This module tests the factory function that builds a PositionIndex from
collected name bindings, including position-aware variable resolution.
"""

from annotation_prioritizer.models import (
    NameBinding,
    NameBindingKind,
    Scope,
    ScopeKind,
    build_position_index,
    make_qualified_name,
)


def test_build_index_with_no_bindings() -> None:
    """Empty bindings list should create empty index."""
    index = build_position_index([])

    # Should resolve to None for any name
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
    result = index.resolve("foo", 10, module_scope)
    assert result is None


def test_build_index_with_single_binding() -> None:
    """Index with single binding should be resolvable."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
    binding = NameBinding(
        name="sqrt",
        line_number=1,
        kind=NameBindingKind.IMPORT,
        qualified_name=None,
        scope_stack=module_scope,
        source_module="math",
        target_class=None,
    )

    index = build_position_index([binding])

    # Should resolve sqrt after line 1
    result = index.resolve("sqrt", 10, module_scope)
    assert result == binding

    # Should not resolve before line 1
    result = index.resolve("sqrt", 1, module_scope)
    assert result is None


def test_build_index_sorts_bindings_by_line_number() -> None:
    """Bindings should be sorted by line number for correct resolution."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    # Create bindings out of order
    binding2 = NameBinding(
        name="foo",
        line_number=20,
        kind=NameBindingKind.FUNCTION,
        qualified_name=make_qualified_name("__module__.foo"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )
    binding1 = NameBinding(
        name="foo",
        line_number=10,
        kind=NameBindingKind.IMPORT,
        qualified_name=None,
        scope_stack=module_scope,
        source_module="bar",
        target_class=None,
    )

    # Build index with out-of-order bindings
    index = build_position_index([binding2, binding1])

    # At line 15, should resolve to the import (line 10)
    result = index.resolve("foo", 15, module_scope)
    assert result == binding1

    # At line 25, should resolve to the function (line 20)
    result = index.resolve("foo", 25, module_scope)
    assert result == binding2


def test_build_index_resolves_variable_to_class() -> None:
    """Variables referencing classes should have target_class resolved."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    class_binding = NameBinding(
        name="Calculator",
        line_number=1,
        kind=NameBindingKind.CLASS,
        qualified_name=make_qualified_name("__module__.Calculator"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    var_binding = NameBinding(
        name="calc",
        line_number=10,
        kind=NameBindingKind.VARIABLE,
        qualified_name=make_qualified_name("__module__.calc"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,  # Unresolved
    )

    # Build index with unresolved variable
    index = build_position_index([class_binding, var_binding], [(var_binding, "Calculator")])

    # The variable should now have target_class resolved
    result = index.resolve("calc", 15, module_scope)
    assert result is not None
    assert result.kind == NameBindingKind.VARIABLE
    assert result.target_class == make_qualified_name("__module__.Calculator")


def test_build_index_variable_resolves_to_shadowed_class() -> None:
    """Variable resolution should respect shadowing (issue #31)."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    # Import Calculator from module
    import_binding = NameBinding(
        name="Calculator",
        line_number=1,
        kind=NameBindingKind.IMPORT,
        qualified_name=None,
        scope_stack=module_scope,
        source_module="external",
        target_class=None,
    )

    # Local Calculator class shadows the import
    class_binding = NameBinding(
        name="Calculator",
        line_number=10,
        kind=NameBindingKind.CLASS,
        qualified_name=make_qualified_name("__module__.Calculator"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # Variable created after the local class
    var_binding = NameBinding(
        name="calc",
        line_number=20,
        kind=NameBindingKind.VARIABLE,
        qualified_name=make_qualified_name("__module__.calc"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    index = build_position_index([import_binding, class_binding, var_binding], [(var_binding, "Calculator")])

    # Variable should resolve to the LOCAL class, not the import
    result = index.resolve("calc", 25, module_scope)
    assert result is not None
    assert result.target_class == make_qualified_name("__module__.Calculator")


def test_build_index_unresolvable_variable_keeps_none() -> None:
    """Variables that can't be resolved should keep target_class=None."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    var_binding = NameBinding(
        name="calc",
        line_number=10,
        kind=NameBindingKind.VARIABLE,
        qualified_name=make_qualified_name("__module__.calc"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # Try to resolve to a class that doesn't exist
    index = build_position_index([var_binding], [(var_binding, "NonexistentClass")])

    result = index.resolve("calc", 15, module_scope)
    assert result is not None
    assert result.target_class is None


def test_build_index_variable_wont_resolve_to_function() -> None:
    """Variables referencing functions should not get target_class set."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    func_binding = NameBinding(
        name="process",
        line_number=1,
        kind=NameBindingKind.FUNCTION,
        qualified_name=make_qualified_name("__module__.process"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    var_binding = NameBinding(
        name="p",
        line_number=10,
        kind=NameBindingKind.VARIABLE,
        qualified_name=make_qualified_name("__module__.p"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # Variable references a function, not a class
    index = build_position_index([func_binding, var_binding], [(var_binding, "process")])

    result = index.resolve("p", 15, module_scope)
    assert result is not None
    assert result.target_class is None  # Should not resolve to function


def test_build_index_variable_wont_resolve_to_import() -> None:
    """Variables referencing imports should not get target_class set."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    import_binding = NameBinding(
        name="math",
        line_number=1,
        kind=NameBindingKind.IMPORT,
        qualified_name=None,
        scope_stack=module_scope,
        source_module="math",
        target_class=None,
    )

    var_binding = NameBinding(
        name="m",
        line_number=10,
        kind=NameBindingKind.VARIABLE,
        qualified_name=make_qualified_name("__module__.m"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # Variable references an import, not a class
    index = build_position_index([import_binding, var_binding], [(var_binding, "math")])

    result = index.resolve("m", 15, module_scope)
    assert result is not None
    assert result.target_class is None  # Should not resolve to import


def test_build_index_shadowing_import_by_function() -> None:
    """Import shadowed by function (issue #31 scenario)."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    # Import: from math import sqrt
    import_binding = NameBinding(
        name="sqrt",
        line_number=1,
        kind=NameBindingKind.IMPORT,
        qualified_name=None,
        scope_stack=module_scope,
        source_module="math",
        target_class=None,
    )

    # Function: def sqrt(): ...
    func_binding = NameBinding(
        name="sqrt",
        line_number=10,
        kind=NameBindingKind.FUNCTION,
        qualified_name=make_qualified_name("__module__.sqrt"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    index = build_position_index([import_binding, func_binding])

    # Before function definition: should resolve to import
    result = index.resolve("sqrt", 5, module_scope)
    assert result == import_binding

    # After function definition: should resolve to function
    result = index.resolve("sqrt", 15, module_scope)
    assert result == func_binding


def test_build_index_shadowing_function_by_import() -> None:
    """Function shadowed by later import (issue #31 scenario)."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    # Function: def sqrt(): ...
    func_binding = NameBinding(
        name="sqrt",
        line_number=1,
        kind=NameBindingKind.FUNCTION,
        qualified_name=make_qualified_name("__module__.sqrt"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # Import: from math import sqrt
    import_binding = NameBinding(
        name="sqrt",
        line_number=10,
        kind=NameBindingKind.IMPORT,
        qualified_name=None,
        scope_stack=module_scope,
        source_module="math",
        target_class=None,
    )

    index = build_position_index([func_binding, import_binding])

    # Before import: should resolve to function
    result = index.resolve("sqrt", 5, module_scope)
    assert result == func_binding

    # After import: should resolve to import
    result = index.resolve("sqrt", 15, module_scope)
    assert result == import_binding


def test_build_index_variable_reassignment() -> None:
    """Multiple assignments to same variable should be tracked."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    class1_binding = NameBinding(
        name="Calculator",
        line_number=1,
        kind=NameBindingKind.CLASS,
        qualified_name=make_qualified_name("__module__.Calculator"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    class2_binding = NameBinding(
        name="AdvancedCalculator",
        line_number=5,
        kind=NameBindingKind.CLASS,
        qualified_name=make_qualified_name("__module__.AdvancedCalculator"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # First assignment to calc variable
    var1_binding = NameBinding(
        name="calc",
        line_number=10,
        kind=NameBindingKind.VARIABLE,
        qualified_name=make_qualified_name("__module__.calc"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # Second assignment to calc variable (reassignment)
    var2_binding = NameBinding(
        name="calc",
        line_number=20,
        kind=NameBindingKind.VARIABLE,
        qualified_name=make_qualified_name("__module__.calc"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    index = build_position_index(
        [class1_binding, class2_binding, var1_binding, var2_binding],
        [(var1_binding, "Calculator"), (var2_binding, "AdvancedCalculator")],
    )

    # At line 15: should resolve to first assignment
    result = index.resolve("calc", 15, module_scope)
    assert result is not None
    assert result.line_number == 10
    assert result.target_class == make_qualified_name("__module__.Calculator")

    # At line 25: should resolve to second assignment
    result = index.resolve("calc", 25, module_scope)
    assert result is not None
    assert result.line_number == 20
    assert result.target_class == make_qualified_name("__module__.AdvancedCalculator")


def test_build_index_multiple_shadows_in_scope() -> None:
    """Multiple shadowing events for the same name (issue #31)."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    # from math import sqrt (line 1)
    import1 = NameBinding(
        name="sqrt",
        line_number=1,
        kind=NameBindingKind.IMPORT,
        qualified_name=None,
        scope_stack=module_scope,
        source_module="math",
        target_class=None,
    )

    # def sqrt(): ... (line 10)
    func = NameBinding(
        name="sqrt",
        line_number=10,
        kind=NameBindingKind.FUNCTION,
        qualified_name=make_qualified_name("__module__.sqrt"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # from numpy import sqrt (line 20)
    import2 = NameBinding(
        name="sqrt",
        line_number=20,
        kind=NameBindingKind.IMPORT,
        qualified_name=None,
        scope_stack=module_scope,
        source_module="numpy",
        target_class=None,
    )

    index = build_position_index([import1, func, import2])

    # Line 5: should resolve to math.sqrt
    result = index.resolve("sqrt", 5, module_scope)
    assert result == import1

    # Line 15: should resolve to local function
    result = index.resolve("sqrt", 15, module_scope)
    assert result == func

    # Line 25: should resolve to numpy.sqrt
    result = index.resolve("sqrt", 25, module_scope)
    assert result == import2


def test_build_index_class_shadows_import() -> None:
    """Class definition shadows import (issue #31 scenario)."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    # Import: from external import Calculator
    import_binding = NameBinding(
        name="Calculator",
        line_number=1,
        kind=NameBindingKind.IMPORT,
        qualified_name=None,
        scope_stack=module_scope,
        source_module="external",
        target_class=None,
    )

    # Class: class Calculator: ...
    class_binding = NameBinding(
        name="Calculator",
        line_number=10,
        kind=NameBindingKind.CLASS,
        qualified_name=make_qualified_name("__module__.Calculator"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    index = build_position_index([import_binding, class_binding])

    # Before class: resolves to import
    result = index.resolve("Calculator", 5, module_scope)
    assert result == import_binding

    # After class: resolves to local class
    result = index.resolve("Calculator", 15, module_scope)
    assert result == class_binding


def test_build_index_variables_in_nested_scope() -> None:
    """Variable resolution works in nested scopes."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)
    func_scope = (Scope(ScopeKind.MODULE, "__module__"), Scope(ScopeKind.FUNCTION, "process"))

    # class Calculator at module level
    class_binding = NameBinding(
        name="Calculator",
        line_number=1,
        kind=NameBindingKind.CLASS,
        qualified_name=make_qualified_name("__module__.Calculator"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # calc = Calculator() inside function
    var_binding = NameBinding(
        name="calc",
        line_number=10,
        kind=NameBindingKind.VARIABLE,
        qualified_name=make_qualified_name("__module__.process.calc"),
        scope_stack=func_scope,
        source_module=None,
        target_class=None,
    )

    index = build_position_index([class_binding, var_binding], [(var_binding, "Calculator")])

    # Variable in function scope should resolve to module-level class
    result = index.resolve("calc", 15, func_scope)
    assert result is not None
    assert result.target_class == make_qualified_name("__module__.Calculator")


def test_build_index_with_no_unresolved_variables() -> None:
    """Index building works when unresolved_variables is None."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    binding = NameBinding(
        name="foo",
        line_number=1,
        kind=NameBindingKind.FUNCTION,
        qualified_name=make_qualified_name("__module__.foo"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # Call with unresolved_variables=None (default)
    index = build_position_index([binding])

    result = index.resolve("foo", 10, module_scope)
    assert result == binding


def test_build_index_with_empty_unresolved_list() -> None:
    """Index building works when unresolved_variables is empty list."""
    module_scope = (Scope(ScopeKind.MODULE, "__module__"),)

    binding = NameBinding(
        name="foo",
        line_number=1,
        kind=NameBindingKind.FUNCTION,
        qualified_name=make_qualified_name("__module__.foo"),
        scope_stack=module_scope,
        source_module=None,
        target_class=None,
    )

    # Call with empty list
    index = build_position_index([binding], [])

    result = index.resolve("foo", 10, module_scope)
    assert result == binding
