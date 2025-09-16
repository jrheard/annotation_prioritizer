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

from .models import CallCount, FunctionInfo, Scope, ScopeKind


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

    visitor = CallCountVisitor(known_functions)
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

        >>> visitor = CallCountVisitor(known_functions)
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

    def __init__(self, known_functions: tuple[FunctionInfo, ...]) -> None:
        """Initialize visitor with functions to track.

        Args:
            known_functions: Functions to count calls for, matched by qualified_name
        """
        super().__init__()
        # Create internal call count tracking from known functions
        self.call_counts: dict[str, int] = {func.qualified_name: 0 for func in known_functions}
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
        # Try to resolve to nested functions first, then fall back to module level
        if isinstance(func, ast.Name):
            return self._resolve_function_call(func.id)

        # Method calls: obj.method_name()
        if isinstance(func, ast.Attribute):
            # Self method calls: self.method_name() - use current scope context
            # TODO: Should we also special-case `cls` in addition to `self`?
            if isinstance(func.value, ast.Name) and func.value.id == "self":
                # Build qualified name from current scope stack, excluding function scopes
                # since self.method() calls should resolve to the class method, not nested function
                scope_names = [scope.name for scope in self._scope_stack if scope.kind != ScopeKind.FUNCTION]
                return ".".join([*scope_names, func.attr])

            # Static/class method calls: ClassName.method_name()
            if isinstance(func.value, ast.Name):
                class_name = func.value.id
                # TODO: is this right? why is `class_name` guaranteed to live directly on `__module__`?
                return f"__module__.{class_name}.{func.attr}"

            # Complex qualified calls: obj.attr.method() or module.submodule.function()
            # Currently simplified to just final attribute
            # - ⚠️ **Future Enhancement Needed**: The current implementation has
            # a limitation with complex qualified calls like
            # `obj.attr1.attr2.method()`. Currently, only the final attribute
            # `"method"` is extracted rather than building the full qualified name.
            if isinstance(func.value, ast.Attribute):
                return f"__module__.{func.attr}"

        # TODO: i think we need a `_resolve_method_call()` fn that works
        # similarly to `_resolve_function_call()`

        # Dynamic calls: getattr(obj, 'method')(), obj[key](), etc.
        # Cannot be resolved statically - return None
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
