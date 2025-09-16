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
        # Internal: Tracks current scope context during traversal for building qualified names.
        # Stack is pushed when entering a scope (class or function) and popped when exiting.
        # Always starts with module scope as the root.
        self._scope_stack: list[Scope] = [Scope(kind=ScopeKind.MODULE, name="__module__")]

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition to track scope context for method calls."""
        self._scope_stack.append(Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition to track scope context for nested function calls."""
        self._scope_stack.append(Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack.pop()

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition to track scope context for nested function calls."""
        self._scope_stack.append(Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack.pop()

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
            # Build qualified name from current scope stack, excluding function scopes
            # since self.method() calls should resolve to the class method, not nested function
            scope_names = [scope.name for scope in self._scope_stack if scope.kind != ScopeKind.FUNCTION]
            return ".".join([*scope_names, func.attr])

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
            return self._extract_nested_method_call(func)

        return None

    def _extract_nested_method_call(self, func: ast.Attribute) -> str | None:
        """Extract qualified name from nested class method calls.

        Handles cases like Outer.Inner.method_name() where the receiver is
        itself an attribute access (nested classes).

        Args:
            func: The ast.Attribute node where func.value is also ast.Attribute

        Returns:
            Qualified method name if resolvable, fallback module-qualified name otherwise
        """
        # Extract the full qualified name like "Outer.Inner"
        qualified_parts: list[str] = []
        current: ast.AST = func.value
        while isinstance(current, ast.Attribute):
            qualified_parts.insert(0, current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            qualified_parts.insert(0, current.id)
            # Try to resolve the full qualified class name
            full_class_name = ".".join(qualified_parts)
            resolved_class = self._resolve_compound_class_name(full_class_name)
            if resolved_class:
                return f"{resolved_class}.{func.attr}"

        # Fall back to existing behavior for complex cases
        return f"__module__.{func.attr}"

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
        # Generate candidate qualified names from most specific to least specific scope
        candidates: list[str] = []

        # For nested function calls, try sibling functions in containing function scopes
        # Work backwards through the scope stack to find function scopes
        for i in range(len(self._scope_stack)):
            if self._scope_stack[i].kind == ScopeKind.FUNCTION:
                # Try resolving as a sibling function in this function's scope
                scope_names = [scope.name for scope in self._scope_stack[: i + 1]]
                candidates.append(".".join([*scope_names, function_name]))

        # Always try module level as fallback
        candidates.append(f"__module__.{function_name}")

        # Return the first candidate that exists in our known functions
        for candidate in candidates:
            if candidate in self.call_counts:
                return candidate

        return None

    def _resolve_compound_class_name(self, compound_name: str) -> str | None:
        """Resolve a compound class name like 'Outer.Inner' to its qualified form.

        Handles cases where a nested class is accessed with dot notation.
        For example, 'Outer.Inner' might resolve to '__module__.Outer.Inner'.

        Args:
            compound_name: The compound name to resolve (e.g., "Outer.Inner")

        Returns:
            Qualified class name if found in registry, None otherwise
        """
        # First, try it as-is with module prefix
        full_qualified = f"__module__.{compound_name}"
        if full_qualified in self._class_registry.ast_classes:
            return full_qualified

        # Try from current scope context
        # Check both function and class scopes (working backwards from most specific)
        for i in range(len(self._scope_stack) - 1, -1, -1):
            scope = self._scope_stack[i]

            # If we're inside a function, the compound name might be relative to that function
            if scope.kind == ScopeKind.FUNCTION:
                # Build scope prefix including the function
                scope_names = [s.name for s in self._scope_stack[: i + 1]]
                candidate = ".".join([*scope_names, compound_name])
                if candidate in self._class_registry.ast_classes:
                    return candidate

            # If we're inside a class, the compound name might be relative to that class
            elif scope.kind == ScopeKind.CLASS:
                # Build scope prefix
                scope_names = [s.name for s in self._scope_stack[: i + 1]]
                candidate = ".".join([*scope_names, compound_name])
                if candidate in self._class_registry.ast_classes:
                    return candidate

        return None

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
        candidates: list[str] = []

        # Build candidates from current scope outward
        # If we're in Outer.method(), seeing "Inner" should check:
        # 1. __module__.Outer.Inner (sibling class)
        # 2. __module__.Inner (module-level class)

        # First, check if we're in a function that might have local classes
        for i in range(len(self._scope_stack) - 1, -1, -1):
            if self._scope_stack[i].kind == ScopeKind.FUNCTION:
                # Try as a class defined in this function
                scope_names = [s.name for s in self._scope_stack[: i + 1]]
                candidates.append(".".join([*scope_names, class_name]))

        # Then check class scopes for sibling classes
        for i in range(len(self._scope_stack)):
            if self._scope_stack[i].kind == ScopeKind.CLASS:
                # Try as sibling class in this class's scope
                scope_names = [s.name for s in self._scope_stack[: i + 1]]
                candidates.append(".".join([*scope_names, class_name]))

        # Always try module level as fallback
        candidates.append(f"__module__.{class_name}")

        # Check built-in types directly (they don't have __module__ prefix)
        if class_name in self._class_registry.builtin_classes:
            return class_name

        # Return first match found in AST classes registry
        for candidate in candidates:
            if candidate in self._class_registry.ast_classes:
                return candidate

        return None
