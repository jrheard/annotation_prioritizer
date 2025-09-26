"""Tests for the ImportRegistry and ImportedName dataclasses."""

from annotation_prioritizer.import_registry import ImportedName, ImportRegistry
from annotation_prioritizer.models import Scope, ScopeKind, make_qualified_name
from annotation_prioritizer.scope_tracker import add_scope, create_initial_stack


def test_import_registry_lookup_module_scope() -> None:
    """Test that imports at module scope are visible throughout the module."""
    # Create an import at module scope
    math_import = ImportedName(
        local_name="math",
        source_module="math",
        original_name=None,
        is_module_import=True,
        relative_level=0,
        scope=make_qualified_name("__module__"),
    )

    registry = ImportRegistry(imports=frozenset([math_import]))

    # Should be visible at module scope
    module_stack = create_initial_stack()
    result = registry.lookup_import("math", module_stack)
    assert result == math_import

    # Should be visible in a function within the module
    function_stack = add_scope(module_stack, Scope(kind=ScopeKind.FUNCTION, name="my_func"))
    result = registry.lookup_import("math", function_stack)
    assert result == math_import

    # Should be visible in a nested class method
    class_stack = add_scope(module_stack, Scope(kind=ScopeKind.CLASS, name="MyClass"))
    method_stack = add_scope(class_stack, Scope(kind=ScopeKind.FUNCTION, name="method"))
    result = registry.lookup_import("math", method_stack)
    assert result == math_import


def test_import_registry_lookup_function_scope() -> None:
    """Test that imports in function scope are only visible within that function."""
    # Create an import inside a function
    json_import = ImportedName(
        local_name="json",
        source_module="json",
        original_name=None,
        is_module_import=True,
        relative_level=0,
        scope=make_qualified_name("__module__.my_func"),
    )

    registry = ImportRegistry(imports=frozenset([json_import]))

    # Should NOT be visible at module scope
    module_stack = create_initial_stack()
    result = registry.lookup_import("json", module_stack)
    assert result is None

    # Should be visible within the function
    function_stack = add_scope(module_stack, Scope(kind=ScopeKind.FUNCTION, name="my_func"))
    result = registry.lookup_import("json", function_stack)
    assert result == json_import

    # Should NOT be visible in a different function
    other_func_stack = add_scope(module_stack, Scope(kind=ScopeKind.FUNCTION, name="other_func"))
    result = registry.lookup_import("json", other_func_stack)
    assert result is None


def test_import_registry_scope_visibility_with_similar_names() -> None:
    """Test that imports in foo() are NOT visible in foo_bar() despite prefix match."""
    # Import in foo() function
    math_import = ImportedName(
        local_name="math",
        source_module="math",
        original_name=None,
        is_module_import=True,
        relative_level=0,
        scope=make_qualified_name("__module__.foo"),
    )

    registry = ImportRegistry(imports=frozenset([math_import]))

    # Create scope stacks for testing
    module_stack = create_initial_stack()

    # Check visibility from foo_bar's scope - should NOT be visible
    foo_bar_stack = add_scope(module_stack, Scope(kind=ScopeKind.FUNCTION, name="foo_bar"))
    result = registry.lookup_import("math", foo_bar_stack)
    assert result is None, "Import in foo() incorrectly visible in foo_bar()"

    # But should be visible from foo's scope
    foo_stack = add_scope(module_stack, Scope(kind=ScopeKind.FUNCTION, name="foo"))
    result = registry.lookup_import("math", foo_stack)
    assert result is not None, "Import should be visible in its own scope"


def test_import_registry_multiple_imports() -> None:
    """Test registry with multiple imports at different scopes."""
    imports = frozenset(
        [
            ImportedName(
                local_name="math",
                source_module="math",
                original_name=None,
                is_module_import=True,
                relative_level=0,
                scope=make_qualified_name("__module__"),
            ),
            ImportedName(
                local_name="List",
                source_module="typing",
                original_name=None,
                is_module_import=False,
                relative_level=0,
                scope=make_qualified_name("__module__"),
            ),
            ImportedName(
                local_name="json",
                source_module="json",
                original_name=None,
                is_module_import=True,
                relative_level=0,
                scope=make_qualified_name("__module__.process_data"),
            ),
        ]
    )

    registry = ImportRegistry(imports=imports)
    module_stack = create_initial_stack()

    # Math and List should be visible at module scope
    assert registry.lookup_import("math", module_stack) is not None
    assert registry.lookup_import("List", module_stack) is not None
    assert registry.lookup_import("json", module_stack) is None

    # All three should be visible inside process_data function
    func_stack = add_scope(module_stack, Scope(kind=ScopeKind.FUNCTION, name="process_data"))
    assert registry.lookup_import("math", func_stack) is not None
    assert registry.lookup_import("List", func_stack) is not None
    assert registry.lookup_import("json", func_stack) is not None

    # Only math and List visible in other functions
    other_stack = add_scope(module_stack, Scope(kind=ScopeKind.FUNCTION, name="other_func"))
    assert registry.lookup_import("math", other_stack) is not None
    assert registry.lookup_import("List", other_stack) is not None
    assert registry.lookup_import("json", other_stack) is None


def test_import_registry_from_import() -> None:
    """Test handling of from-imports (non-module imports)."""
    sqrt_import = ImportedName(
        local_name="sqrt",
        source_module="math",
        original_name=None,
        is_module_import=False,  # from math import sqrt
        relative_level=0,
        scope=make_qualified_name("__module__"),
    )

    registry = ImportRegistry(imports=frozenset([sqrt_import]))
    module_stack = create_initial_stack()

    result = registry.lookup_import("sqrt", module_stack)
    assert result == sqrt_import
    assert result is not None
    assert result.is_module_import is False


def test_import_registry_aliased_import() -> None:
    """Test handling of aliased imports."""
    pd_import = ImportedName(
        local_name="pd",  # Used as 'pd' in code
        source_module="pandas",  # Actual module is 'pandas'
        original_name=None,
        is_module_import=True,
        relative_level=0,
        scope=make_qualified_name("__module__"),
    )

    registry = ImportRegistry(imports=frozenset([pd_import]))
    module_stack = create_initial_stack()

    # Should find by local name 'pd'
    result = registry.lookup_import("pd", module_stack)
    assert result == pd_import

    # Should NOT find by original module name 'pandas'
    result = registry.lookup_import("pandas", module_stack)
    assert result is None


def test_import_registry_relative_import() -> None:
    """Test handling of relative imports."""
    relative_import = ImportedName(
        local_name="utils",
        source_module=None,  # Relative imports don't have source module
        original_name=None,
        is_module_import=False,
        relative_level=1,  # from . import utils
        scope=make_qualified_name("__module__"),
    )

    registry = ImportRegistry(imports=frozenset([relative_import]))
    module_stack = create_initial_stack()

    result = registry.lookup_import("utils", module_stack)
    assert result == relative_import
    assert result is not None
    assert result.relative_level == 1


def test_import_registry_empty() -> None:
    """Test empty import registry."""
    registry = ImportRegistry(imports=frozenset())
    module_stack = create_initial_stack()

    result = registry.lookup_import("anything", module_stack)
    assert result is None


def test_import_registry_class_method_visibility() -> None:
    """Test that module imports are visible in class methods."""
    typing_import = ImportedName(
        local_name="typing",
        source_module="typing",
        original_name=None,
        is_module_import=True,
        relative_level=0,
        scope=make_qualified_name("__module__"),
    )

    registry = ImportRegistry(imports=frozenset([typing_import]))

    # Build stack: module -> class -> method
    module_stack = create_initial_stack()
    class_stack = add_scope(module_stack, Scope(kind=ScopeKind.CLASS, name="MyClass"))
    method_stack = add_scope(class_stack, Scope(kind=ScopeKind.FUNCTION, name="__init__"))

    result = registry.lookup_import("typing", method_stack)
    assert result == typing_import
