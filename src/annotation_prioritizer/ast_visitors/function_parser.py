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
    - Scope-aware qualified names: Functions are tracked with their full scope context
      (e.g., "__module__.Calculator.add" for methods, "__module__.outer_func.inner_func" for nested functions)
      to distinguish them from other functions with the same name.
    - Conservative extraction: Only handles statically defined functions; dynamic
      function creation (via exec, type(), etc.) is intentionally not supported.
    - Complete scope tracking: Maintains a stack of both class and function scopes
      during AST traversal to build accurate qualified names for nested structures.

The module's primary entry point is parse_function_definitions(), which returns
FunctionInfo objects containing all extracted metadata.

Relationship to Other Modules:
    - models.py: Defines the FunctionInfo, ParameterInfo, Scope, and ScopeKind data structures
    - call_counter.py: Uses function definitions to resolve and count calls
    - analyzer.py: Combines definitions and call counts to compute priorities

Limitations:
    - Intentional: No support for dynamically created functions (exec, type(), etc.)
    - Intentional: No type inference for unannotated parameters
    - Not Yet Implemented: Import and inheritance resolution
"""

import ast
from pathlib import Path
from typing import override

from annotation_prioritizer.ast_arguments import ArgumentKind, iter_all_arguments
from annotation_prioritizer.ast_visitors.class_discovery import ClassRegistry
from annotation_prioritizer.models import (
    FunctionInfo,
    ParameterInfo,
    Scope,
    ScopeKind,
    make_qualified_name,
)
from annotation_prioritizer.scope_tracker import (
    ScopeStack,
    add_scope,
    build_qualified_name,
    create_initial_stack,
    drop_last_scope,
)


def _extract_parameters(args: ast.arguments) -> tuple[ParameterInfo, ...]:
    """Extract comprehensive parameter information from a function's arguments.

    Args:
        args: AST arguments node containing all parameter information from a
              function definition.

    Returns:
        Tuple of ParameterInfo objects representing all parameters in definition
        order. Each ParameterInfo indicates the parameter's name, whether it has
        a type annotation, and special properties (variadic, keyword).
    """
    parameters: list[ParameterInfo] = []

    for arg, kind in iter_all_arguments(args):
        parameters.append(
            ParameterInfo(
                name=arg.arg,
                has_annotation=arg.annotation is not None,
                is_variadic=kind == ArgumentKind.VAR_POSITIONAL,
                is_keyword=kind == ArgumentKind.VAR_KEYWORD,
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

    The visitor maintains state during traversal to track scope nesting (classes and
    functions), which is essential for building qualified names like
    "OuterClass.InnerClass.method" and "OuterClass.method.inner_func". This
    scope-aware naming ensures that nested functions and methods are properly
    distinguished during call counting and analysis.

    Traversal Behavior:
        Classes and functions are tracked for building qualified names. FunctionDef
        and AsyncFunctionDef nodes trigger extraction of full function metadata. The
        visitor continues traversing into nested structures to find all functions,
        including nested functions and methods in nested classes.

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
        - Tracks both class and function scopes for accurate qualified naming
    """

    def __init__(self, file_path: Path) -> None:
        """Initialize the visitor with source file context.

        Args:
            file_path: Path to the Python source file being analyzed.
                      This path is stored with each FunctionInfo for traceability.
        """
        super().__init__()
        # Public API: Accumulates FunctionInfo objects as functions are discovered.
        # Each function's metadata is captured at the point of definition.
        self.functions: list[FunctionInfo] = []
        # Internal: Source file path to include in each FunctionInfo for traceability
        self._file_path = file_path
        # Internal: Tracks current scope context during traversal for building qualified names.
        # Maintains an immutable scope stack that is replaced when entering/exiting scopes.
        # Always starts with module scope as the root.
        self._scope_stack: ScopeStack = create_initial_stack()

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class context for building qualified method names.

        Maintains the scope to enable proper qualified name construction for
        methods. For nested classes, this creates names like "Outer.Inner.method".

        Args:
            node: AST node representing a class definition.

        Side Effects:
            Pushes class scope to _scope before traversing the class body,
            then pops it after traversal completes. This ensures methods get
            the correct qualified names.
        """
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Extract metadata from a regular function definition.

        Processes the function node to extract its signature information and adds
        it to the functions list. Pushes the function onto the scope before
        traversing nested functions to ensure proper qualified naming.

        Args:
            node: AST node representing a function definition.

        Side Effects:
            Adds a FunctionInfo object to self.functions.
            Pushes function scope to _scope_stack, calls generic_visit to
            traverse nested functions, then pops the function scope.
        """
        # First record the function with the current scope
        self._process_function(node)
        # Then push the function scope and traverse nested definitions
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Extract metadata from an async function definition.

        Handles async functions identically to regular functions since the
        annotation priority analysis doesn't distinguish between them. Pushes
        the function onto the scope before traversing nested functions.

        Args:
            node: AST node representing an async function definition.

        Side Effects:
            Adds a FunctionInfo object to self.functions.
            Pushes function scope to _scope_stack, calls generic_visit to
            traverse nested functions, then pops the function scope.
        """
        # First record the function with the current scope
        self._process_function(node)
        # Then push the function scope and traverse nested definitions
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

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
        qualified_name = build_qualified_name(self._scope_stack, node.name)
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


def generate_synthetic_init_methods(
    known_functions: tuple[FunctionInfo, ...],
    class_registry: ClassRegistry,
    file_path: Path,
) -> tuple[FunctionInfo, ...]:
    """Generate synthetic __init__ methods for classes without explicit ones.

    Creates a FunctionInfo with a single 'self' parameter (no annotations) for
    each class that doesn't already have an __init__ method defined.

    Note: Does not infer parameters from parent classes. This is a limitation
    that will be addressed when inheritance support is implemented.

    Args:
        known_functions: Already discovered functions to check for existing __init__
        class_registry: Registry of all classes found in the AST
        file_path: Path to the source file for the FunctionInfo objects

    Returns:
        Tuple of synthetic FunctionInfo objects for missing __init__ methods
    """
    # Build a set of existing __init__ qualified names for faster lookup
    existing_init_names = {func.qualified_name for func in known_functions if func.name == "__init__"}

    # Find classes that need synthetic __init__ methods
    classes_needing_init = [
        class_name
        for class_name in class_registry.classes
        if make_qualified_name(f"{class_name}.__init__") not in existing_init_names
    ]

    # Create synthetic __init__ for each class that needs one
    synthetic_inits: list[FunctionInfo] = []
    for class_name in classes_needing_init:
        synthetic_init = FunctionInfo(
            name="__init__",
            qualified_name=make_qualified_name(f"{class_name}.__init__"),
            parameters=(
                ParameterInfo(
                    name="self",
                    has_annotation=False,
                    is_variadic=False,
                    is_keyword=False,
                ),
            ),
            has_return_annotation=False,
            line_number=0,  # Line 0 indicates synthetic
            file_path=file_path,
        )
        synthetic_inits.append(synthetic_init)

    return tuple(synthetic_inits)


def parse_function_definitions(
    tree: ast.Module,
    file_path: Path,
    class_registry: ClassRegistry,
) -> tuple[FunctionInfo, ...]:
    """Extract all function definitions from a parsed AST.

    Now includes synthetic __init__ methods for classes without explicit constructors.

    Args:
        tree: Parsed AST module
        file_path: Path to the source file (for FunctionInfo objects)
        class_registry: Registry of known classes

    Returns:
        Tuple of FunctionInfo objects containing function metadata including
        name, qualified name, parameters, and return annotation status.
    """
    visitor = FunctionDefinitionVisitor(file_path)
    visitor.visit(tree)

    # Generate synthetic __init__ methods for classes without them
    synthetic_inits = generate_synthetic_init_methods(tuple(visitor.functions), class_registry, file_path)

    return tuple(visitor.functions) + synthetic_inits
