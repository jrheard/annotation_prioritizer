"""AST-based counting of function calls for annotation priority analysis.

This module traverses Python source files to count how many times each known function
is called. These call counts feed into the priority analysis to identify frequently-used
functions that lack type annotations.

The call counter uses conservative resolution - it only counts calls it can confidently
attribute to specific functions. Ambiguous or dynamic calls are excluded from counts
rather than guessed at, ensuring accuracy over completeness.

Key Design Decisions:
    - Conservative attribution: Only count calls we're confident about
    - Qualified name matching: Uses full qualified names (e.g., "Calculator.add")
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

from .models import CallCount, FunctionInfo


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

    # Create mapping from qualified names to track calls
    known_function_names = {func.qualified_name for func in known_functions}
    call_counts: dict[str, int] = dict.fromkeys(known_function_names, 0)

    visitor = CallCountVisitor(call_counts)
    visitor.visit(tree)

    return tuple(
        CallCount(function_qualified_name=name, call_count=count) for name, count in call_counts.items()
    )


class CallCountVisitor(ast.NodeVisitor):
    """AST visitor that counts calls to known functions.

    Traverses the AST to identify and count function calls, maintaining context
    about the current class scope to properly resolve self.method() calls.
    Uses conservative resolution - when the target of a call cannot be determined
    with confidence, it is not counted rather than guessed at.

    Usage:
        After calling visit() on an AST tree, access the 'call_counts' dictionary
        to retrieve the updated call counts for each function:

        >>> visitor = CallCountVisitor(call_counts_dict)
        >>> visitor.visit(tree)
        >>> updated_counts = visitor.call_counts

    Call Resolution Patterns:
        Currently handles:
        - Direct function calls: function_name()
        - Self method calls: self.method_name() (uses class context)
        - Static/class method calls: ClassName.method_name()

        Not yet implemented:
        - Instance method calls: obj.method_name() where obj is a variable
        - Imported function calls: imported_module.function()
        - Chained calls: obj.attr.method()

    The visitor maintains state during traversal (_class_stack) to track the
    current class context, enabling proper resolution of self.method() calls
    to their qualified names (e.g., "Calculator.add").
    """

    def __init__(self, call_counts: dict[str, int]) -> None:
        """Initialize visitor with call count tracking dictionary."""
        super().__init__()
        self.call_counts = call_counts
        # Internal: Tracks current class context during traversal for building qualified names
        # Stack is pushed when entering a class and popped when exiting
        self._class_stack: list[str] = []

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition to track context for method calls."""
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

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

        # Direct calls to module-level functions: function_name()
        if isinstance(func, ast.Name):
            return func.id

        # Method calls: obj.method_name()
        if isinstance(func, ast.Attribute):
            # Self method calls: self.method_name() - use current class context
            if isinstance(func.value, ast.Name) and func.value.id == "self":
                if self._class_stack:
                    return ".".join([*self._class_stack, func.attr])
                return func.attr

            # Static/class method calls: ClassName.method_name()
            if isinstance(func.value, ast.Name):
                class_name = func.value.id
                return f"{class_name}.{func.attr}"

            # Complex qualified calls: obj.attr.method() or module.submodule.function()
            # Currently simplified to just final attribute - full resolution not yet implemented
            if isinstance(func.value, ast.Attribute):
                return func.attr

        # Dynamic calls: getattr(obj, 'method')(), obj[key](), etc.
        # Cannot be resolved statically - return None
        return None
