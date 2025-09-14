"""AST-based extraction of function definitions for type annotation analysis.

This module provides the foundation for the annotation prioritizer's static analysis
by extracting detailed metadata about all function definitions in Python source files.
It uses Python's Abstract Syntax Tree (AST) module to parse source code without
executing it.

The parser identifies all callable entities (functions, methods, async functions) and
extracts their signatures, including parameter information and return type annotations.
This metadata feeds into the call counter and analyzer modules to determine which
functions are frequently called but lack proper type annotations.

Key Design Decisions:
    - Qualified names: Methods are tracked with their full class context (e.g.,
      "Calculator.add") to distinguish them from module-level functions with the same name.
    - Conservative extraction: Only handles statically defined functions; dynamic
      function creation (via exec, type(), etc.) is intentionally not supported.

The module's primary entry point is parse_function_definitions(), which returns
FunctionInfo objects containing all extracted metadata.

Relationship to Other Modules:
    - models.py: Defines the FunctionInfo and ParameterInfo data structures
    - call_counter.py: Uses function definitions to resolve and count calls
    - analyzer.py: Combines definitions and call counts to compute priorities

Limitations:
    - Intentional: No support for dynamically created functions (exec, type(), etc.)
    - Intentional: No type inference for unannotated parameters
    - Temporary: Import and inheritance resolution not yet implemented
"""

import ast
from pathlib import Path
from typing import override

from .models import FunctionInfo, ParameterInfo


def _extract_parameters(args: ast.arguments) -> tuple[ParameterInfo, ...]:
    """Extract comprehensive parameter information from a function's arguments.

    Processes all parameter types supported by Python: regular positional arguments,
    positional-only arguments (Python 3.8+), keyword-only arguments, *args, and
    **kwargs. For each parameter, captures its name and whether it has a type
    annotation, plus special flags for variadic parameters.

    Args:
        args: AST arguments node containing all parameter information from a
              function definition.

    Returns:
        Tuple of ParameterInfo objects representing all parameters in definition
        order. Each ParameterInfo indicates the parameter's name, whether it has
        a type annotation, and special properties (variadic, keyword).
    """
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


class FunctionDefinitionVisitor(ast.NodeVisitor):
    """AST visitor that extracts function definitions and their metadata.

    This visitor implements the standard ast.NodeVisitor pattern to traverse Python
    Abstract Syntax Trees and extract comprehensive information about all function
    definitions. It handles regular functions, async functions, and methods within
    classes, building qualified names that preserve the full context of where each
    function is defined.

    The visitor maintains state during traversal to track class nesting, which is
    essential for building qualified names like "OuterClass.InnerClass.method".
    This context-aware naming ensures that methods with identical names in different
    classes are properly distinguished during call counting and analysis.

    Traversal Behavior:
        Classes are used solely for building qualified method names (e.g., 'Calculator.add'),
        not analyzed as entities. FunctionDef and AsyncFunctionDef nodes trigger
        extraction of full function metadata. The visitor continues traversing into
        nested structures to find all functions, including nested functions and
        methods in nested classes.

    Usage:
        After calling visit() on an AST tree, access the 'functions' attribute to
        retrieve the collected FunctionInfo objects:

        >>> visitor = FunctionDefinitionVisitor(file_path)
        >>> visitor.visit(tree)
        >>> extracted_functions = visitor.functions

    Design Notes:
        - Uses generic_visit() to ensure complete traversal of nested structures
        - Treats async functions identically to regular functions for metadata extraction
        - Does not attempt to resolve inherited methods or overrides
        - Preserves all parameter types (positional, keyword-only, *args, **kwargs)
    """

    def __init__(self, file_path: str) -> None:
        """Initialize the visitor with source file context.

        Args:
            file_path: Absolute or relative path to the Python source file being analyzed.
                      This path is stored with each FunctionInfo for traceability.
        """
        super().__init__()
        # Public API: Accumulates FunctionInfo objects as functions are discovered.
        # Each function's metadata is captured at the point of definition.
        self.functions: list[FunctionInfo] = []
        # Internal: Source file path to include in each FunctionInfo for traceability
        self._file_path = file_path
        # Internal: Tracks current class context during traversal for building qualified names.
        # Stack is pushed when entering a class and popped when exiting.
        self._class_stack: list[str] = []

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class context for building qualified method names.

        Maintains the class_stack to enable proper qualified name construction for
        methods. For nested classes, this creates names like "Outer.Inner.method".

        Args:
            node: AST node representing a class definition.

        Side Effects:
            Pushes class name to _class_stack before traversing the class body,
            then pops it after traversal completes. This ensures methods get
            the correct qualified names.
        """
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Extract metadata from a regular function definition.

        Processes the function node to extract its signature information and adds
        it to the functions list. Continues traversal to find nested functions.

        Args:
            node: AST node representing a function definition.

        Side Effects:
            Adds a FunctionInfo object to self.functions.
            Calls generic_visit to traverse nested functions.
        """
        self._process_function(node)
        self.generic_visit(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Extract metadata from an async function definition.

        Handles async functions identically to regular functions since the
        annotation priority analysis doesn't distinguish between them.

        Args:
            node: AST node representing an async function definition.

        Side Effects:
            Adds a FunctionInfo object to self.functions.
            Calls generic_visit to traverse nested functions.
        """
        self._process_function(node)
        self.generic_visit(node)

    def _process_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Extract and store metadata from a function definition node.

        Central processing logic for both regular and async functions. Builds the
        qualified name, extracts parameters, checks for return annotation, and
        creates a FunctionInfo object with all metadata.

        Args:
            node: AST node for either a regular or async function definition.

        Side Effects:
            Appends a new FunctionInfo object to self.functions.
        """
        qualified_name = self._build_qualified_name(node.name)
        parameters = _extract_parameters(node.args)
        has_return_annotation = node.returns is not None

        function_info = FunctionInfo(
            name=node.name,
            qualified_name=qualified_name,
            parameters=parameters,
            has_return_annotation=has_return_annotation,
            line_number=node.lineno,
            file_path=self._file_path,
        )

        self.functions.append(function_info)

    def _build_qualified_name(self, function_name: str) -> str:
        """Construct a fully qualified name using the current class context.

        For methods, prepends the class name(s) to create qualified names like
        "ClassName.method_name" or "Outer.Inner.method_name". For module-level
        functions, returns the name unchanged.

        Args:
            function_name: The local name of the function or method.

        Returns:
            Qualified name string that uniquely identifies the function within
            the module's namespace.
        """
        if self._class_stack:
            return ".".join([*self._class_stack, function_name])
        return function_name


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
