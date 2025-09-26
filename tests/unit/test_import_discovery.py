"""Tests for import discovery and registry building."""

import ast

from annotation_prioritizer.ast_visitors.import_discovery import build_import_registry
from annotation_prioritizer.models import Scope, ScopeKind, make_qualified_name
from annotation_prioritizer.scope_tracker import add_scope, create_initial_stack


def test_simple_import() -> None:
    """Test basic import statement."""
    source = "import math"
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 1
    assert imports[0].local_name == "math"
    assert imports[0].source_module == "math"
    assert imports[0].is_module_import is True
    assert imports[0].relative_level == 0
    assert imports[0].scope == make_qualified_name("__module__")


def test_aliased_import() -> None:
    """Test import with alias."""
    source = "import pandas as pd"
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 1
    assert imports[0].local_name == "pd"
    assert imports[0].source_module == "pandas"
    assert imports[0].is_module_import is True
    assert imports[0].original_name is None  # module imports don't have original_name


def test_from_import() -> None:
    """Test from-import statement."""
    source = "from typing import List, Dict"
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 2

    names = {imp.local_name for imp in imports}
    assert names == {"List", "Dict"}

    for imp in imports:
        assert imp.source_module == "typing"
        assert imp.is_module_import is False
        assert imp.relative_level == 0


def test_from_import_with_alias() -> None:
    """Test from-import with aliasing."""
    source = "from collections import defaultdict as dd"
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 1
    assert imports[0].local_name == "dd"
    assert imports[0].source_module == "collections"
    assert imports[0].original_name == "defaultdict"
    assert imports[0].is_module_import is False


def test_relative_import() -> None:
    """Test relative imports."""
    source = """\
from . import utils
from ..models import User
from ...lib import helper
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 3

    # Check relative levels
    utils_import = next(i for i in imports if i.local_name == "utils")
    assert utils_import.relative_level == 1
    assert utils_import.source_module is None

    user_import = next(i for i in imports if i.local_name == "User")
    assert user_import.relative_level == 2
    assert user_import.source_module == "models"

    helper_import = next(i for i in imports if i.local_name == "helper")
    assert helper_import.relative_level == 3
    assert helper_import.source_module == "lib"


def test_nested_import_in_function() -> None:
    """Test import inside function has correct scope."""
    source = """\
import math  # Module level

def my_function():
    import json  # Function level
    from typing import Optional

def another_function():
    import csv
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 4

    # Check scopes
    math_import = next(i for i in imports if i.local_name == "math")
    assert math_import.scope == make_qualified_name("__module__")

    json_import = next(i for i in imports if i.local_name == "json")
    assert json_import.scope == make_qualified_name("__module__.my_function")

    optional_import = next(i for i in imports if i.local_name == "Optional")
    assert optional_import.scope == make_qualified_name("__module__.my_function")

    csv_import = next(i for i in imports if i.local_name == "csv")
    assert csv_import.scope == make_qualified_name("__module__.another_function")


def test_nested_import_in_class() -> None:
    """Test import inside class has correct scope."""
    source = """\
class MyClass:
    import json
    from typing import Optional

    def method(self):
        import csv
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 3

    json_import = next(i for i in imports if i.local_name == "json")
    assert json_import.scope == make_qualified_name("__module__.MyClass")

    optional_import = next(i for i in imports if i.local_name == "Optional")
    assert optional_import.scope == make_qualified_name("__module__.MyClass")

    csv_import = next(i for i in imports if i.local_name == "csv")
    assert csv_import.scope == make_qualified_name("__module__.MyClass.method")


def test_star_import_ignored() -> None:
    """Test that star imports are skipped."""
    source = "from math import *"
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    assert len(registry.imports) == 0  # Star import should be ignored


def test_multiple_imports_same_module() -> None:
    """Test multiple imports from the same module."""
    source = """\
import math
from math import sqrt, sin, cos
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 4

    # Module import
    math_import = next(i for i in imports if i.local_name == "math")
    assert math_import.is_module_import is True

    # Function imports
    for name in ["sqrt", "sin", "cos"]:
        func_import = next(i for i in imports if i.local_name == name)
        assert func_import.source_module == "math"
        assert func_import.is_module_import is False


def test_dotted_module_import() -> None:
    """Test import of module with dots in name."""
    source = """\
import xml.etree.ElementTree
import xml.etree.ElementTree as ET
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 2

    # Full name import
    full_import = next(i for i in imports if i.local_name == "xml.etree.ElementTree")
    assert full_import.source_module == "xml.etree.ElementTree"
    assert full_import.is_module_import is True

    # Aliased import
    et_import = next(i for i in imports if i.local_name == "ET")
    assert et_import.source_module == "xml.etree.ElementTree"
    assert et_import.is_module_import is True


def test_async_function_import() -> None:
    """Test imports inside async functions."""
    source = """\
async def async_func():
    import asyncio
    from typing import Awaitable
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 2

    for imp in imports:
        assert imp.scope == make_qualified_name("__module__.async_func")


def test_empty_file_no_imports() -> None:
    """Test that files with no imports return empty registry."""
    source = """\
def func():
    pass

class MyClass:
    pass
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    assert len(registry.imports) == 0


def test_scope_visibility_with_similar_names() -> None:
    """Test that imports in foo() are NOT visible in foo_bar() despite prefix match."""
    source = """\
def foo():
    import math

def foo_bar():
    pass  # Should NOT see math import from foo()
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    # Create scope stacks for testing
    foo_bar_stack = create_initial_stack()
    foo_bar_stack = add_scope(foo_bar_stack, Scope(kind=ScopeKind.FUNCTION, name="foo_bar"))

    # math import from foo() should NOT be visible in foo_bar()
    result = registry.lookup_import("math", foo_bar_stack)
    assert result is None, "Import in foo() incorrectly visible in foo_bar()"

    # But should be visible from foo's scope
    foo_stack = create_initial_stack()
    foo_stack = add_scope(foo_stack, Scope(kind=ScopeKind.FUNCTION, name="foo"))

    result = registry.lookup_import("math", foo_stack)
    assert result is not None, "Import should be visible in its own scope"


def test_import_visibility_in_nested_scopes() -> None:
    """Test import visibility across nested scopes."""
    source = """\
import module_level

class OuterClass:
    import class_level

    def method(self):
        import method_level

        def nested():
            import nested_level
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    # Build various scope stacks to test visibility
    module_stack = create_initial_stack()
    class_stack = add_scope(module_stack, Scope(kind=ScopeKind.CLASS, name="OuterClass"))
    method_stack = add_scope(class_stack, Scope(kind=ScopeKind.FUNCTION, name="method"))
    nested_stack = add_scope(method_stack, Scope(kind=ScopeKind.FUNCTION, name="nested"))

    # Test visibility from nested function - should see all parent imports
    assert registry.lookup_import("module_level", nested_stack) is not None
    assert registry.lookup_import("class_level", nested_stack) is not None
    assert registry.lookup_import("method_level", nested_stack) is not None
    assert registry.lookup_import("nested_level", nested_stack) is not None

    # Test visibility from method - should not see nested_level
    assert registry.lookup_import("module_level", method_stack) is not None
    assert registry.lookup_import("class_level", method_stack) is not None
    assert registry.lookup_import("method_level", method_stack) is not None
    assert registry.lookup_import("nested_level", method_stack) is None

    # Test visibility from class - should not see method_level or nested_level
    assert registry.lookup_import("module_level", class_stack) is not None
    assert registry.lookup_import("class_level", class_stack) is not None
    assert registry.lookup_import("method_level", class_stack) is None
    assert registry.lookup_import("nested_level", class_stack) is None


def test_conditional_imports() -> None:
    """Test that conditional imports are tracked with their actual scope."""
    source = """\
if TYPE_CHECKING:
    from typing import List, Dict

try:
    import numpy as np
except ImportError:
    import array
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    # Should track all imports regardless of conditions
    assert len(imports) == 4

    # All should be at module scope
    for imp in imports:
        assert imp.scope == make_qualified_name("__module__")

    # Check specific imports exist
    names = {imp.local_name for imp in imports}
    assert names == {"List", "Dict", "np", "array"}


def test_import_with_multiple_aliases() -> None:
    """Test importing multiple items with different aliases."""
    source = "from typing import List as L, Dict as D, Optional"
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 3

    # Check aliased imports
    list_import = next(i for i in imports if i.local_name == "L")
    assert list_import.original_name == "List"
    assert list_import.source_module == "typing"

    dict_import = next(i for i in imports if i.local_name == "D")
    assert dict_import.original_name == "Dict"
    assert dict_import.source_module == "typing"

    # Check non-aliased import
    optional_import = next(i for i in imports if i.local_name == "Optional")
    assert optional_import.original_name is None
    assert optional_import.source_module == "typing"
