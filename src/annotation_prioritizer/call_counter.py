"""AST parsing for counting function calls within the same module."""

import ast
from pathlib import Path

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
    """AST visitor to count function calls."""

    def __init__(self, call_counts: dict[str, int]) -> None:
        """Initialize visitor with call count tracking dictionary."""
        self.call_counts = call_counts
        self.class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition to track context for method calls."""
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function call to count calls to known functions."""
        call_name = self._extract_call_name(node)
        if call_name and call_name in self.call_counts:
            self.call_counts[call_name] += 1

        self.generic_visit(node)

    def _extract_call_name(self, node: ast.Call) -> str | None:
        """Extract the qualified name of the called function."""
        func = node.func

        # Direct function call: function_name()
        if isinstance(func, ast.Name):
            return func.id

        # Method call: obj.method_name()
        if isinstance(func, ast.Attribute):
            # Handle self.method_name() calls
            if isinstance(func.value, ast.Name) and func.value.id == "self":
                # Build qualified name with current class context
                if self.class_stack:
                    return ".".join([*self.class_stack, func.attr])
                return func.attr

            # Handle ClassName.static_method() calls
            if isinstance(func.value, ast.Name):
                class_name = func.value.id
                return f"{class_name}.{func.attr}"

            # Handle qualified calls within same module (e.g., outer.inner.method)
            if isinstance(func.value, ast.Attribute):
                # This could be a more complex qualified name
                # For now, we'll extract just the final attribute
                return func.attr

        return None
