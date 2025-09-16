"""AST-based counting of function calls for annotation priority analysis.

This module traverses Python source files to count how many times each known function
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
    - analyzer.py: Combines call counts with function definitions for prioritization
    - models.py: Defines CallCount data structure

Limitations:
    - Intentional: No support for star imports (from module import *)
    - Intentional: No support for dynamic method calls (getattr, exec, etc.)
    - Not Yet Implemented: Cross-module call tracking (import resolution)
    - Not Yet Implemented: Instance method calls via variables (e.g., calc.add())
    - Not Yet Implemented: Inheritance resolution for method calls
"""

import ast
from pathlib import Path
from typing import override

from annotation_prioritizer.class_discovery import ClassRegistry, build_class_registry
from annotation_prioritizer.models import CallCount, FunctionInfo, Scope, ScopeKind
from annotation_prioritizer.scope_tracker import (
    ScopeState,
    build_qualified_name,
    extract_attribute_chain,
    find_first_match,
    generate_name_candidates,
)


def count_function_calls(file_path: str, known_functions: tuple[FunctionInfo, ...]) -> tuple[CallCount, ...]:
    """Count calls to known functions within the same file using AST parsing.

    Parses the Python source file and identifies calls to functions from the
    known_functions list. Handles direct function calls, method calls on self,
    and class method calls. Returns empty tuple if file doesn't exist or has
    syntax errors.

    Args:
        file_path: Path to the Python source file to analyze
        known_functions: Functions to count calls for, matched by qualified_name

    Returns:
        Tuple of CallCount objects with call counts for each known function.
        Functions with zero calls are still included in the results.

    """
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        return ()

    try:
        source_code = file_path_obj.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=file_path)
    except (OSError, SyntaxError):
        return ()

    class_registry = build_class_registry(tree)
    visitor = CallCountVisitor(known_functions, class_registry)
    visitor.visit(tree)

    return tuple(
        CallCount(function_qualified_name=name, call_count=count)
        for name, count in visitor.call_counts.items()
    )


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

    The visitor maintains state during traversal (_scope_stack) to track the
    current scope context, enabling proper resolution of self.method() calls
    to their qualified names (e.g., "__module__.Calculator.add").
    """

    def __init__(self, known_functions: tuple[FunctionInfo, ...], class_registry: ClassRegistry) -> None:
        """Initialize visitor with functions to track and class registry.

        Args:
            known_functions: Functions to count calls for
            class_registry: Registry of known classes for definitive identification
        """
        super().__init__()
        # Create internal call count tracking from known functions
        self.call_counts: dict[str, int] = {func.qualified_name: 0 for func in known_functions}
        self._class_registry = class_registry
        self._scope = ScopeState()

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition to track scope context for method calls."""
        self._scope.push(Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition to track scope context for nested function calls."""
        self._scope.push(Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope.pop()

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition to track scope context for nested function calls."""
        self._scope.push(Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope.pop()

    @override
    def visit_Call(self, node: ast.Call) -> None:
        """Visit function call to count calls to known functions."""
        call_name = self._extract_call_name(node)
        if call_name and call_name in self.call_counts:
            self.call_counts[call_name] += 1

        self.generic_visit(node)

    def _extract_call_name(self, node: ast.Call) -> str | None:
        """Extract the qualified name of the called function.

        Uses conservative resolution - only returns names for calls that can be
        confidently attributed to specific functions. Ambiguous or dynamic calls
        return None and are excluded from counting.

        Returns:
            Qualified function name if resolvable, None otherwise.
        """
        func = node.func

        # Direct calls to functions: function_name()
        if isinstance(func, ast.Name):
            return self._resolve_function_call(func.id)

        # Method calls: obj.method_name()
        if isinstance(func, ast.Attribute):
            return self._extract_method_call(func)

        # Dynamic calls: getattr(obj, 'method')(), obj[key](), etc.
        # Cannot be resolved statically - return None
        return None

    def _extract_method_call(self, func: ast.Attribute) -> str | None:
        """Extract qualified name from a method call (attribute access).

        Handles self.method(), ClassName.method(), and Outer.Inner.method() calls.

        Args:
            func: The ast.Attribute node representing the method call

        Returns:
            Qualified method name if resolvable, None otherwise
        """
        # Self method calls: self.method_name() - use current scope context
        # TODO: Should we also special-case `cls` in addition to `self`?
        if isinstance(func.value, ast.Name) and func.value.id == "self":
            # Build qualified name from current scope, excluding function scopes
            # since self.method() calls should resolve to the class method, not nested function
            return build_qualified_name(
                self._scope.stack, func.attr, exclude_kinds=frozenset({ScopeKind.FUNCTION})
            )

        # Static/class method calls: ClassName.method_name()
        if isinstance(func.value, ast.Name):
            potential_class = func.value.id
            # Use resolver to check all possible scopes
            resolved_class = self._resolve_class_name(potential_class)
            if resolved_class:
                return f"{resolved_class}.{func.attr}"
            # Not a class - might be a variable (TODO future work)
            return None

        # Nested class method calls: Outer.Inner.method_name()
        if isinstance(func.value, ast.Attribute):
            # Extract the chain of attributes
            chain = extract_attribute_chain(func.value)
            full_class_name = ".".join(chain)
            resolved_class = self._resolve_compound_class_name(full_class_name)
            if resolved_class:
                return f"{resolved_class}.{func.attr}"

            # Fall back to module-qualified name for unresolvable complex cases
            # This handles cases like variable.attribute.method() where variable isn't a known class
            return f"__module__.{func.attr}"

        return None

    def _resolve_function_call(self, function_name: str) -> str | None:
        """Resolve a direct function call to its qualified name.

        Tries to resolve the function call by checking different scope levels,
        starting from more specific (nested) scopes and falling back to module level.
        Only returns names for functions that exist in the known functions list.

        Args:
            function_name: The local name of the function being called

        Returns:
            Qualified function name if found in known functions, None otherwise
        """
        candidates = generate_name_candidates(self._scope.stack, function_name)
        return find_first_match(candidates, set(self.call_counts.keys()))

    def _resolve_compound_class_name(self, compound_name: str) -> str | None:
        """Resolve a compound class name like 'Outer.Inner' to its qualified form.

        Handles cases where a nested class is accessed with dot notation.
        For example, 'Outer.Inner' might resolve to '__module__.Outer.Inner'.

        Args:
            compound_name: The compound name to resolve (e.g., "Outer.Inner")

        Returns:
            Qualified class name if found in registry, None otherwise
        """
        candidates = generate_name_candidates(self._scope.stack, compound_name)
        return find_first_match(candidates, self._class_registry.ast_classes)

    def _resolve_class_name(self, class_name: str) -> str | None:
        """Resolve a class name to its qualified form based on current scope.

        Checks from most specific (nested class) to least specific (module) scope.
        This handles cases like:
        - Inner.method() inside Outer class -> __module__.Outer.Inner
        - Calculator.add() at module level -> __module__.Calculator

        NOTE: Currently only resolves classes defined in the current file and Python
        built-in types. Imported classes (from typing, collections, third-party packages)
        are not recognized and their method calls won't be counted.

        Args:
            class_name: The local name to resolve (e.g., "Calculator", "Inner")

        Returns:
            Qualified class name if found in registry, None otherwise

        Examples:
            "Calculator" -> "__module__.Calculator" (if defined in file)
            "int" -> "int" (built-in type)
            "List" -> None (imported from typing, not yet supported)
            "defaultdict" -> None (imported from collections, not yet supported)
        """
        # Check built-in types directly (they don't have __module__ prefix)
        if class_name in self._class_registry.builtin_classes:
            return class_name

        # Generate candidates and check against registry
        candidates = generate_name_candidates(self._scope.stack, class_name)
        return find_first_match(candidates, self._class_registry.ast_classes)
