"""AST-based counting of function calls for annotation priority analysis.

This module traverses Python ASTs to count how many times each known function
is called. These call counts feed into the priority analysis to identify frequently-used
functions that lack type annotations.

The call counter uses conservative resolution - it only counts calls it can confidently
attribute to specific functions. Ambiguous or dynamic calls are excluded from counts
rather than guessed at, ensuring accuracy over completeness.

Key Design Decisions:
    - Conservative attribution: Only count calls we're confident about
    - Qualified name matching: Uses full qualified names (e.g., "__module__.Calculator.add")
      to distinguish methods from module-level functions

Relationship to Other Modules:
    - function_parser.py: Provides the FunctionInfo definitions to count calls for
    - analyzer.py: Orchestrates analysis, provides AST and registries
    - models.py: Defines CallCount data structure
    - variable_registry.py: Provides utilities for variable type lookup

Limitations:
    - Intentional: No support for star imports (from module import *)
    - Intentional: No support for dynamic method calls (getattr, exec, etc.)
    - Not Yet Implemented: Cross-module call tracking (import resolution)
    - Not Yet Implemented: Inheritance resolution for method calls
"""

import ast
import builtins
from typing import override

from annotation_prioritizer.ast_visitors.class_discovery import ClassRegistry
from annotation_prioritizer.models import (
    CallCount,
    FunctionInfo,
    QualifiedName,
    Scope,
    ScopeKind,
    UnresolvableCall,
    make_qualified_name,
)
from annotation_prioritizer.scope_tracker import (
    add_scope,
    create_initial_stack,
    drop_last_scope,
    extract_attribute_chain,
    resolve_name_in_scope,
)
from annotation_prioritizer.variable_registry import VariableRegistry, lookup_variable

# Maximum length for unresolvable call text before truncation
MAX_UNRESOLVABLE_CALL_LENGTH = 200


def _is_builtin_call(node: ast.Call) -> bool:
    """Check if a call is to a Python built-in function.

    Only checks direct calls to built-ins (e.g., print(), len()).
    Does not check method calls on built-in types (e.g., list.append()).

    Args:
        node: The AST Call node to check

    Returns:
        True if this is a call to a built-in function, False otherwise
    """
    if isinstance(node.func, ast.Name):
        # Only consider callable attributes of builtins module
        name = node.func.id
        return hasattr(builtins, name) and callable(getattr(builtins, name))
    return False


def count_function_calls(
    tree: ast.Module,
    known_functions: tuple[FunctionInfo, ...],
    class_registry: ClassRegistry,
    variable_registry: VariableRegistry,
    source_code: str,
) -> tuple[tuple[CallCount, ...], tuple[UnresolvableCall, ...]]:
    """Count calls to known functions in the AST.

    Args:
        tree: Parsed AST module
        known_functions: Functions to count calls for
        class_registry: Registry of known classes
        variable_registry: Registry of variable type information
        source_code: Source code for error context

    Returns:
        Tuple of (resolved call counts, unresolvable calls)
    """
    visitor = CallCountVisitor(known_functions, class_registry, source_code, variable_registry)
    visitor.visit(tree)

    resolved = tuple(
        CallCount(function_qualified_name=name, call_count=count)
        for name, count in visitor.call_counts.items()
    )

    return (resolved, visitor.get_unresolvable_calls())


class CallCountVisitor(ast.NodeVisitor):
    """AST visitor that counts calls to known functions.

    Traverses the AST to identify and count function calls, maintaining context
    about the current scope (classes and functions) to properly resolve self.method() calls.
    Uses conservative resolution - when the target of a call cannot be determined
    with confidence, it is not counted rather than guessed at.

    Usage:
        After calling visit() on an AST tree, access the 'call_counts' dictionary
        to retrieve the updated call counts for each function:

        >>> visitor = CallCountVisitor(known_functions, class_registry)
        >>> visitor.visit(tree)
        >>> call_counts = visitor.call_counts

    Call Resolution Patterns:
        Currently handles:
        - Direct function calls: function_name()
        - Self method calls: self.method_name() (uses scope context)
        - Static/class method calls: ClassName.method_name()

        Not yet implemented:
        - Instance method calls: obj.method_name() where obj is a variable
        - Imported function calls: imported_module.function()
        - Chained calls: obj.attr.method()

    The visitor maintains scope state during traversal (_scope_stack) to track the
    current scope context, enabling proper resolution of self.method() calls
    to their qualified names (e.g., "__module__.Calculator.add").
    """

    def __init__(
        self,
        known_functions: tuple[FunctionInfo, ...],
        class_registry: ClassRegistry,
        source_code: str,
        variable_registry: VariableRegistry,
    ) -> None:
        """Initialize visitor with functions to track and registries.

        Args:
            known_functions: Functions to count calls for
            class_registry: Registry of known classes for definitive identification
            source_code: Source code for extracting unresolvable call text
            variable_registry: Registry of variable types for resolution
        """
        super().__init__()
        # Create internal call count tracking from known functions
        self.call_counts: dict[QualifiedName, int] = {func.qualified_name: 0 for func in known_functions}
        self._class_registry = class_registry
        self._scope_stack = create_initial_stack()
        self._source_code = source_code
        self._variable_registry = variable_registry
        self._unresolvable_calls: list[UnresolvableCall] = []

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition to track scope context for method calls."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition to track scope context for nested function calls."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition to track scope context for nested function calls."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        """Visit function call to count calls to known functions."""
        call_name = self._resolve_call_name(node)
        if call_name and call_name in self.call_counts:
            self.call_counts[call_name] += 1
        elif call_name is None and not _is_builtin_call(node):
            self._track_unresolvable_call(node)

        self.generic_visit(node)

    def get_unresolvable_calls(self) -> tuple[UnresolvableCall, ...]:
        """Get all unresolvable calls found during traversal."""
        return tuple(self._unresolvable_calls)

    def _track_unresolvable_call(self, node: ast.Call) -> None:
        """Track a call that cannot be resolved to a known function.

        Uses ast.get_source_segment() to extract the exact call text, handling
        multi-line calls and complex expressions correctly.

        Args:
            node: The AST Call node that couldn't be resolved
        """
        call_text = ast.get_source_segment(self._source_code, node)
        if not call_text:
            call_text = "<unable to extract call text>"

        # Truncate very long calls while preserving readability
        if len(call_text) > MAX_UNRESOLVABLE_CALL_LENGTH:
            call_text = call_text[:MAX_UNRESOLVABLE_CALL_LENGTH] + "..."

        unresolvable = UnresolvableCall(
            line_number=node.lineno,
            call_text=call_text,
        )
        self._unresolvable_calls.append(unresolvable)

    def _resolve_call_name(self, node: ast.Call) -> QualifiedName | None:
        """Resolve the qualified name of the called function.

        Uses conservative resolution - only returns names for calls that can be
        confidently attributed to specific functions. Ambiguous or dynamic calls
        return None and are excluded from counting.

        Returns:
            Qualified function name if resolvable, None otherwise.
        """
        func = node.func

        # Direct calls to functions: function_name()
        # TODO: could actually be a class name: Calculator()
        if isinstance(func, ast.Name):
            return self._resolve_function_call(func.id)

        # Method calls: obj.method_name()
        # TODO: once we support imports, this might not always be a method - could be eg `math.random()`
        if isinstance(func, ast.Attribute):
            return self._resolve_method_call(func)

        # Dynamic calls: getattr(obj, 'method')(), obj[key](), etc.
        # Cannot be resolved statically - return None
        return None

    def _extract_class_name_from_value(self, node: ast.expr) -> str | None:
        """Extract a class name from an AST node.

        Handles both simple names (ast.Name) and compound names (ast.Attribute).
        Returns None for unsupported node types or complex expressions.

        Args:
            node: The AST node to extract from (typically func.value)

        Returns:
            Class name as string if extractable, None otherwise

        Examples:
            ast.Name(id="Calculator") -> "Calculator"
            ast.Attribute chain for Outer.Inner -> "Outer.Inner"
            ast.Call or other complex nodes -> None
        """
        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Attribute):
            try:
                chain = extract_attribute_chain(node)
                return ".".join(chain)
            except AssertionError:
                # Complex expressions like foo()[0].bar aren't supported
                return None

        # Other node types (Call, Subscript, etc.) can't be class references
        return None

    def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
        """Resolve qualified name from a method call (attribute access).

        Handles self.method(), ClassName.method(), variable.method(), and
        Outer.Inner.method() calls.

        Args:
            func: The ast.Attribute node representing the method call

        Returns:
            Qualified method name if resolvable, None otherwise
        """
        # Check if it's a call on a variable
        if isinstance(func.value, ast.Name):
            variable_name = func.value.id

            # Look up the variable's type
            variable_type = lookup_variable(self._variable_registry, self._scope_stack, variable_name)

            if variable_type:
                # Build the qualified method name for both instances and class refs
                return make_qualified_name(f"{variable_type.class_name}.{func.attr}")

        # All other class method calls: extract class name and resolve
        class_name = self._extract_class_name_from_value(func.value)
        if not class_name:
            # Not a resolvable class reference (e.g., complex expression)
            return None

        # Try to resolve the class name to its qualified form
        resolved_class = self._resolve_class_name(class_name)
        if resolved_class:
            return make_qualified_name(f"{resolved_class}.{func.attr}")

        # Class name couldn't be resolved in any scope or registry
        return None

    def _resolve_function_call(self, function_name: str) -> QualifiedName | None:
        """Resolve a function call to its qualified name."""
        return resolve_name_in_scope(self._scope_stack, function_name, self.call_counts.keys())

    def _resolve_class_name(self, class_name: str) -> QualifiedName | None:
        """Resolve a class name to its qualified name."""
        return resolve_name_in_scope(self._scope_stack, class_name, self._class_registry.classes)
