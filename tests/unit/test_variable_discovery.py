"""Unit tests for variable discovery AST visitor."""

import ast

from annotation_prioritizer.ast_visitors.class_discovery import build_class_registry
from annotation_prioritizer.ast_visitors.variable_discovery import (
    VariableDiscoveryVisitor,
    build_variable_registry,
)
from annotation_prioritizer.models import make_qualified_name


def test_direct_instantiation() -> None:
    """Test that calc = Calculator() creates a tracked variable."""
    code = """
class Calculator:
    pass

calc = Calculator()
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Variable should be tracked at module level
    variable = registry.variables.get(make_qualified_name("__module__.calc"))
    assert variable is not None
    assert variable.class_name == make_qualified_name("__module__.Calculator")
    assert variable.is_instance is True


def test_parameter_annotations() -> None:
    """Test that function parameter annotations are tracked."""
    code = """
class Calculator:
    pass

def process(calc: Calculator):
    pass
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Parameter should be tracked in function scope
    variable = registry.variables.get(make_qualified_name("__module__.process.calc"))
    assert variable is not None
    assert variable.class_name == make_qualified_name("__module__.Calculator")
    assert variable.is_instance is True


def test_variable_annotations() -> None:
    """Test that annotated variables are tracked."""
    code = """
class Calculator:
    pass

calc: Calculator = get_calculator()
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Annotated variable should be tracked
    variable = registry.variables.get(make_qualified_name("__module__.calc"))
    assert variable is not None
    assert variable.class_name == make_qualified_name("__module__.Calculator")
    assert variable.is_instance is True


def test_reassignment_tracking() -> None:
    """Test that reassigned variables use their most recent type."""
    code = """
class Calculator:
    pass

class Helper:
    pass

obj = Calculator()
obj = Helper()  # Reassignment - should track Helper
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Variable should have the most recent type
    variable = registry.variables.get(make_qualified_name("__module__.obj"))
    assert variable is not None
    assert variable.class_name == make_qualified_name("__module__.Helper")
    assert variable.is_instance is True


def test_scope_isolation() -> None:
    """Test that variables with the same name in different scopes are isolated."""
    code = """
class Calculator:
    pass

calc = Calculator()  # Module-level

def func1():
    calc = Calculator()  # Function-level
    pass

def func2():
    calc = Calculator()  # Different function
    pass
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Each scope should have its own variable
    module_var = registry.variables.get(make_qualified_name("__module__.calc"))
    func1_var = registry.variables.get(make_qualified_name("__module__.func1.calc"))
    func2_var = registry.variables.get(make_qualified_name("__module__.func2.calc"))

    assert module_var is not None
    assert func1_var is not None
    assert func2_var is not None
    assert all(
        v.class_name == make_qualified_name("__module__.Calculator")
        for v in [module_var, func1_var, func2_var]
    )


def test_nested_function_parent_scope_access() -> None:
    """Test that nested functions create variables in their own scope."""
    code = """
class Calculator:
    pass

def outer():
    calc = Calculator()

    def inner():
        nested_calc = Calculator()
        pass
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Both outer and inner variables should be tracked
    outer_var = registry.variables.get(make_qualified_name("__module__.outer.calc"))
    inner_var = registry.variables.get(make_qualified_name("__module__.outer.inner.nested_calc"))

    assert outer_var is not None
    assert inner_var is not None
    assert outer_var.class_name == make_qualified_name("__module__.Calculator")
    assert inner_var.class_name == make_qualified_name("__module__.Calculator")


def test_module_level_variable_tracking() -> None:
    """Test that module-level variables are properly tracked."""
    code = """
class Calculator:
    pass

# Various module-level assignments
calc1 = Calculator()
calc2: Calculator = get_calculator()
calc3: Calculator
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # All module-level variables should be tracked
    calc1 = registry.variables.get(make_qualified_name("__module__.calc1"))
    calc2 = registry.variables.get(make_qualified_name("__module__.calc2"))
    calc3 = registry.variables.get(make_qualified_name("__module__.calc3"))

    assert calc1 is not None
    assert calc2 is not None
    assert calc3 is not None
    assert all(v.class_name == make_qualified_name("__module__.Calculator") for v in [calc1, calc2, calc3])


def test_class_references_vs_instances() -> None:
    """Test that class references are distinguished from instances."""
    code = """
class Calculator:
    pass

calc_instance = Calculator()  # Instance
calc_class = Calculator  # Class reference
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    instance_var = registry.variables.get(make_qualified_name("__module__.calc_instance"))
    class_var = registry.variables.get(make_qualified_name("__module__.calc_class"))

    assert instance_var is not None
    assert class_var is not None
    assert instance_var.is_instance is True
    assert class_var.is_instance is False
    assert instance_var.class_name == make_qualified_name("__module__.Calculator")
    assert class_var.class_name == make_qualified_name("__module__.Calculator")


def test_build_variable_registry_orchestration() -> None:
    """Test the build_variable_registry orchestration function."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

def use_calculator(calc: Calculator):
    calc = Calculator()  # Reassignment
    return calc.add(1, 2)
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)

    # Use the orchestration function
    registry = build_variable_registry(tree, class_registry)

    # Check that variables were discovered
    param_var = registry.variables.get(make_qualified_name("__module__.use_calculator.calc"))
    assert param_var is not None
    assert param_var.class_name == make_qualified_name("__module__.Calculator")
    assert param_var.is_instance is True


def test_class_inside_function() -> None:
    """Test that variables can reference classes defined inside functions."""
    code = """
def create_calculator():
    class Calculator:
        pass

    calc = Calculator()
    return calc
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Variable should reference the function-local class
    variable = registry.variables.get(make_qualified_name("__module__.create_calculator.calc"))
    assert variable is not None
    assert variable.class_name == make_qualified_name("__module__.create_calculator.Calculator")
    assert variable.is_instance is True


def test_nested_class_instantiation() -> None:
    """Test variables of nested class types."""
    code = """
class Outer:
    class Inner:
        pass

inner = Outer.Inner()  # Not supported yet (would need attribute resolution)
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # This pattern is not supported yet
    variable = registry.variables.get(make_qualified_name("__module__.inner"))
    assert variable is None


def test_unknown_class_not_tracked() -> None:
    """Test that variables of unknown types are not tracked."""
    code = """
# No Calculator class defined
calc = Calculator()  # Should not be tracked
obj: UnknownType  # Should not be tracked
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # No variables should be tracked since classes are unknown
    assert len(registry.variables) == 0


def test_complex_annotations_not_supported() -> None:
    """Test that complex type annotations are not yet supported."""
    code = """
from typing import Optional, List

class Calculator:
    pass

calc1: Optional[Calculator]  # Not supported
calc2: List[Calculator]  # Not supported
calc3: Calculator | None  # Not supported
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Complex annotations should not be tracked (yet)
    assert len(registry.variables) == 0


def test_multiple_assignment_targets_not_supported() -> None:
    """Test that multiple assignment targets are not supported."""
    code = """
class Calculator:
    pass

# Multiple targets - not supported
calc1, calc2 = Calculator(), Calculator()
calc3 = calc4 = Calculator()
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Multiple assignment patterns should not be tracked
    assert len(registry.variables) == 0


def test_method_parameters_in_class() -> None:
    """Test that method parameters are tracked with correct scope."""
    code = """
class Calculator:
    def process(self, helper: Helper):
        pass

class Helper:
    pass
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Method parameter should be tracked in method scope
    variable = registry.variables.get(make_qualified_name("__module__.Calculator.process.helper"))
    assert variable is not None
    assert variable.class_name == make_qualified_name("__module__.Helper")
    assert variable.is_instance is True

    # self parameter is not tracked (not annotated)
    self_var = registry.variables.get(make_qualified_name("__module__.Calculator.process.self"))
    assert self_var is None


def test_async_function_parameters() -> None:
    """Test that async function parameters are tracked."""
    code = """
class Calculator:
    pass

async def process_async(calc: Calculator):
    pass
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Async function parameter should be tracked
    variable = registry.variables.get(make_qualified_name("__module__.process_async.calc"))
    assert variable is not None
    assert variable.class_name == make_qualified_name("__module__.Calculator")
    assert variable.is_instance is True


def test_variable_in_comprehension_not_tracked() -> None:
    """Test that variables in comprehensions are not tracked (complex scope)."""
    code = """
class Calculator:
    pass

# Comprehension variables - complex scope, not tracked
calcs = [Calculator() for _ in range(5)]
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Only the outer assignment might be tracked (but not as Calculator type)
    assert len(registry.variables) == 0


def test_empty_registry() -> None:
    """Test behavior with empty code."""
    code = ""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    assert len(registry.variables) == 0


def test_annotation_without_assignment() -> None:
    """Test variable annotation without assignment."""
    code = """
class Calculator:
    pass

calc: Calculator  # Annotation without assignment
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Should still track the annotated variable
    variable = registry.variables.get(make_qualified_name("__module__.calc"))
    assert variable is not None
    assert variable.class_name == make_qualified_name("__module__.Calculator")
    assert variable.is_instance is True


def test_complex_annotated_assignment_target() -> None:
    """Test that complex annotated assignment targets are not tracked."""
    code = """
class Calculator:
    pass

# Complex target - not a simple name
self.calc: Calculator = Calculator()
obj.attr: Calculator = Calculator()
items[0]: Calculator = Calculator()
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Complex targets should not be tracked
    assert len(registry.variables) == 0


def test_assignment_to_non_class_name() -> None:
    """Test that assignments of non-class names are not tracked."""
    code = """
class Calculator:
    pass

# some_function is not a class
def some_function():
    pass

calc = some_function  # Should not be tracked as Calculator type
obj = unknown_name  # Should not be tracked
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Non-class assignments should not be tracked
    assert len(registry.variables) == 0


def test_all_parameter_types_tracked() -> None:
    """Test that all Python parameter types are tracked correctly."""
    code = """
class A:
    pass

class B:
    pass

class C:
    pass

def process_all_types(
    pos_only: A, /, regular: B, *args: C, keyword_only: A, **kwargs: B
):
    pass
"""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    registry = visitor.get_registry()

    # Verify all parameter types are tracked
    prefix = "__module__.process_all_types."
    assert registry.variables.get(make_qualified_name(f"{prefix}pos_only")) is not None
    assert registry.variables.get(make_qualified_name(f"{prefix}regular")) is not None
    assert registry.variables.get(make_qualified_name(f"{prefix}args")) is not None
    assert registry.variables.get(make_qualified_name(f"{prefix}keyword_only")) is not None
    assert registry.variables.get(make_qualified_name(f"{prefix}kwargs")) is not None

    # Verify correct class names are tracked
    assert registry.variables[make_qualified_name(f"{prefix}pos_only")].class_name == make_qualified_name(
        "__module__.A"
    )
    assert registry.variables[make_qualified_name(f"{prefix}regular")].class_name == make_qualified_name(
        "__module__.B"
    )
    assert registry.variables[make_qualified_name(f"{prefix}args")].class_name == make_qualified_name(
        "__module__.C"
    )
    assert registry.variables[make_qualified_name(f"{prefix}keyword_only")].class_name == make_qualified_name(
        "__module__.A"
    )
    assert registry.variables[make_qualified_name(f"{prefix}kwargs")].class_name == make_qualified_name(
        "__module__.B"
    )
