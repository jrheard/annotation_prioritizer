"""AST parsing for function definitions."""

import ast
from pathlib import Path
from typing import override

from .models import FunctionInfo, ParameterInfo


def parse_function_definitions(file_path: str) -> tuple[FunctionInfo, ...]:
    """Extract all function definitions from a Python file using AST parsing.

    Parses the Python source file and extracts information about all function
    definitions found, including regular functions, async functions, and methods
    within classes. Builds qualified names for methods using class context.
    Returns empty tuple if file doesn't exist or has syntax errors.

    Args:
        file_path: Path to the Python source file to analyze

    Returns:
        Tuple of FunctionInfo objects containing function metadata including
        name, qualified name, parameters, and return annotation status.
    """
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        return ()

    try:
        source_code = file_path_obj.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=file_path)
    except (OSError, SyntaxError):
        return ()

    visitor = FunctionDefinitionVisitor(file_path)
    visitor.visit(tree)
    return tuple(visitor.functions)


class FunctionDefinitionVisitor(ast.NodeVisitor):
    """AST visitor to extract function definitions."""

    def __init__(self, file_path: str) -> None:
        """Initialize the visitor with a file path."""
        self.file_path = file_path
        self.functions: list[FunctionInfo] = []
        self.class_stack: list[str] = []

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition to track context for method qualified names."""
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition to extract function info."""
        self._process_function(node)
        self.generic_visit(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition to extract function info."""
        self._process_function(node)
        self.generic_visit(node)

    def _process_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Process a function or async function definition."""
        qualified_name = self._build_qualified_name(node.name)
        parameters = self._extract_parameters(node.args)
        has_return_annotation = node.returns is not None

        function_info = FunctionInfo(
            name=node.name,
            qualified_name=qualified_name,
            parameters=parameters,
            has_return_annotation=has_return_annotation,
            line_number=node.lineno,
            file_path=self.file_path,
        )

        self.functions.append(function_info)

    def _build_qualified_name(self, function_name: str) -> str:
        """Build qualified name based on class context."""
        if self.class_stack:
            return ".".join([*self.class_stack, function_name])
        return function_name

    def _extract_parameters(self, args: ast.arguments) -> tuple[ParameterInfo, ...]:
        """Extract parameter information from function arguments."""
        parameters: list[ParameterInfo] = []

        # Regular positional arguments
        parameters.extend(
            [
                ParameterInfo(
                    name=arg.arg,
                    has_annotation=arg.annotation is not None,
                    is_variadic=False,
                    is_keyword=False,
                )
                for arg in args.args
            ]
        )

        # Positional-only arguments (Python 3.8+)
        parameters.extend(
            [
                ParameterInfo(
                    name=arg.arg,
                    has_annotation=arg.annotation is not None,
                    is_variadic=False,
                    is_keyword=False,
                )
                for arg in args.posonlyargs
            ]
        )

        # Keyword-only arguments
        parameters.extend(
            [
                ParameterInfo(
                    name=arg.arg,
                    has_annotation=arg.annotation is not None,
                    is_variadic=False,
                    is_keyword=False,
                )
                for arg in args.kwonlyargs
            ]
        )

        # *args parameter
        if args.vararg is not None:
            parameters.append(
                ParameterInfo(
                    name=args.vararg.arg,
                    has_annotation=args.vararg.annotation is not None,
                    is_variadic=True,
                    is_keyword=False,
                )
            )

        # **kwargs parameter
        if args.kwarg is not None:
            parameters.append(
                ParameterInfo(
                    name=args.kwarg.arg,
                    has_annotation=args.kwarg.annotation is not None,
                    is_variadic=False,
                    is_keyword=True,
                )
            )

        return tuple(parameters)
