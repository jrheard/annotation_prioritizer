"""Unit tests for the variable_registry module."""

from annotation_prioritizer.models import Scope, ScopeKind, make_qualified_name
from annotation_prioritizer.scope_tracker import add_scope, create_initial_stack
from annotation_prioritizer.variable_registry import (
    VariableRegistry,
    VariableType,
    lookup_variable,
)


def test_lookup_variable_in_current_scope() -> None:
    """Test that lookup_variable finds variables in the current scope."""
    # Create a registry with a variable in a function scope
    registry = VariableRegistry(
        variables={
            make_qualified_name("__module__.my_function.calc"): VariableType(
                class_name=make_qualified_name("__module__.Calculator"),
                is_instance=True,
            )
        }
    )

    # Create a scope stack inside my_function
    scope_stack = create_initial_stack()
    scope_stack = add_scope(scope_stack, Scope(kind=ScopeKind.FUNCTION, name="my_function"))

    # Should find the variable
    result = lookup_variable(registry, scope_stack, "calc")
    assert result is not None
    assert result.class_name == "__module__.Calculator"
    assert result.is_instance is True


def test_lookup_variable_in_parent_scope() -> None:
    """Test that lookup_variable finds variables in parent scopes."""
    # Create a registry with a module-level variable
    registry = VariableRegistry(
        variables={
            make_qualified_name("__module__.global_calc"): VariableType(
                class_name=make_qualified_name("__module__.Calculator"),
                is_instance=True,
            )
        }
    )

    # Create a scope stack inside a function (no local variable)
    scope_stack = create_initial_stack()
    scope_stack = add_scope(scope_stack, Scope(kind=ScopeKind.FUNCTION, name="my_function"))

    # Should find the module-level variable from within the function
    result = lookup_variable(registry, scope_stack, "global_calc")
    assert result is not None
    assert result.class_name == "__module__.Calculator"
    assert result.is_instance is True


def test_lookup_variable_with_shadowing() -> None:
    """Test that inner scope variables shadow outer scope ones."""
    # Create a registry with same variable name in different scopes
    registry = VariableRegistry(
        variables={
            make_qualified_name("__module__.calc"): VariableType(
                class_name=make_qualified_name("__module__.OuterCalculator"),
                is_instance=True,
            ),
            make_qualified_name("__module__.my_function.calc"): VariableType(
                class_name=make_qualified_name("__module__.InnerCalculator"),
                is_instance=True,
            ),
        }
    )

    # Create a scope stack inside my_function
    scope_stack = create_initial_stack()
    scope_stack = add_scope(scope_stack, Scope(kind=ScopeKind.FUNCTION, name="my_function"))

    # Should find the inner scope variable (shadowing the outer one)
    result = lookup_variable(registry, scope_stack, "calc")
    assert result is not None
    assert result.class_name == "__module__.InnerCalculator"
    assert result.is_instance is True


def test_lookup_variable_not_found() -> None:
    """Test that lookup_variable returns None for non-existent variables."""
    # Create an empty registry
    registry = VariableRegistry(variables={})

    scope_stack = create_initial_stack()
    result = lookup_variable(registry, scope_stack, "non_existent")
    assert result is None


def test_lookup_variable_with_empty_scope_stack() -> None:
    """Test that lookup_variable works with just the module scope."""
    # Create a registry with a module-level variable
    registry = VariableRegistry(
        variables={
            make_qualified_name("__module__.calc"): VariableType(
                class_name=make_qualified_name("__module__.Calculator"),
                is_instance=True,
            )
        }
    )

    # Use initial stack (just module scope)
    scope_stack = create_initial_stack()

    # Should find the module-level variable
    result = lookup_variable(registry, scope_stack, "calc")
    assert result is not None
    assert result.class_name == "__module__.Calculator"
    assert result.is_instance is True


def test_lookup_variable_with_class_reference() -> None:
    """Test that VariableType correctly tracks class references vs instances."""
    # Create a registry with a class reference (not an instance)
    registry = VariableRegistry(
        variables={
            make_qualified_name("__module__.MyClass"): VariableType(
                class_name=make_qualified_name("__module__.Calculator"),
                is_instance=False,  # This is a class reference, not an instance
            )
        }
    )

    scope_stack = create_initial_stack()
    result = lookup_variable(registry, scope_stack, "MyClass")
    assert result is not None
    assert result.class_name == "__module__.Calculator"
    assert result.is_instance is False  # Correctly identifies as class reference


def test_lookup_variable_in_nested_function() -> None:
    """Test that nested functions can access parent function variables."""
    # Create a registry with a variable in outer function
    registry = VariableRegistry(
        variables={
            make_qualified_name("__module__.outer_func.calc"): VariableType(
                class_name=make_qualified_name("__module__.Calculator"),
                is_instance=True,
            )
        }
    )

    # Create a scope stack inside a nested function
    scope_stack = create_initial_stack()
    scope_stack = add_scope(scope_stack, Scope(kind=ScopeKind.FUNCTION, name="outer_func"))
    scope_stack = add_scope(scope_stack, Scope(kind=ScopeKind.FUNCTION, name="inner_func"))

    # Should find the variable from outer function
    result = lookup_variable(registry, scope_stack, "calc")
    assert result is not None
    assert result.class_name == "__module__.Calculator"
    assert result.is_instance is True


def test_lookup_variable_in_method() -> None:
    """Test that methods can access class-level and module-level variables."""
    # Create a registry with variables at different levels
    registry = VariableRegistry(
        variables={
            make_qualified_name("__module__.module_calc"): VariableType(
                class_name=make_qualified_name("__module__.ModuleCalc"),
                is_instance=True,
            ),
            make_qualified_name("__module__.MyClass.method.local_calc"): VariableType(
                class_name=make_qualified_name("__module__.LocalCalc"),
                is_instance=True,
            ),
        }
    )

    # Create a scope stack inside a method
    scope_stack = create_initial_stack()
    scope_stack = add_scope(scope_stack, Scope(kind=ScopeKind.CLASS, name="MyClass"))
    scope_stack = add_scope(scope_stack, Scope(kind=ScopeKind.FUNCTION, name="method"))

    # Should find the local variable
    result = lookup_variable(registry, scope_stack, "local_calc")
    assert result is not None
    assert result.class_name == "__module__.LocalCalc"

    # Should also find the module-level variable
    result = lookup_variable(registry, scope_stack, "module_calc")
    assert result is not None
    assert result.class_name == "__module__.ModuleCalc"


def test_variable_registry_key_format() -> None:
    """Test that registry keys match the expected format for scope resolution."""
    # Test various key formats
    registry = VariableRegistry(
        variables={
            make_qualified_name("__module__.var1"): VariableType(
                class_name=make_qualified_name("__module__.Type1"), is_instance=True
            ),
            make_qualified_name("__module__.func.var2"): VariableType(
                class_name=make_qualified_name("__module__.Type2"), is_instance=True
            ),
            make_qualified_name("__module__.Class.method.var3"): VariableType(
                class_name=make_qualified_name("__module__.Type3"), is_instance=True
            ),
        }
    )

    # Verify keys are in the expected format
    assert make_qualified_name("__module__.var1") in registry.variables
    assert make_qualified_name("__module__.func.var2") in registry.variables
    assert make_qualified_name("__module__.Class.method.var3") in registry.variables
