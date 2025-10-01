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
    - analyzer.py: Orchestrates analysis, provides AST and PositionIndex
    - models.py: Defines CallCount data structure
    - position_index.py: Provides position-aware name resolution for variable type lookup

Limitations:
    - Intentional: No support for star imports (from module import *)
    - Intentional: No support for dynamic method calls (getattr, exec, etc.)
    - Not Yet Implemented: Cross-module call tracking (import resolution)
    - Not Yet Implemented: Inheritance resolution for method calls
"""

import ast
import builtins
from typing import override

from annotation_prioritizer.models import (
    CallCount,
    FunctionInfo,
    NameBinding,
    NameBindingKind,
    QualifiedName,
    Scope,
    ScopeKind,
    UnresolvableCall,
    make_qualified_name,
)
from annotation_prioritizer.position_index import PositionIndex, resolve_name
from annotation_prioritizer.scope_tracker import (
    add_scope,
    create_initial_stack,
    drop_last_scope,
    get_containing_class_qualified_name,
    get_execution_context,
)

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


def _extract_attribute_chain(node: ast.Attribute) -> list[str] | None:
    """Extract attribute chain from compound reference like Outer.Inner.

    Args:
        node: The ast.Attribute node representing the compound reference

    Returns:
        List of attribute parts like ['Outer', 'Inner'], or None if the chain
        doesn't start with a simple name (e.g., starts with a function call)
    """
    parts = [node.attr]
    current = node.value

    while isinstance(current, ast.Attribute):
        parts.insert(0, current.attr)
        current = current.value

    # The leftmost part should be a Name
    if not isinstance(current, ast.Name):
        return None

    parts.insert(0, current.id)
    return parts


def count_function_calls(
    tree: ast.Module,
    known_functions: tuple[FunctionInfo, ...],
    position_index: PositionIndex,
    known_classes: set[QualifiedName],
    source_code: str,
) -> tuple[tuple[CallCount, ...], tuple[UnresolvableCall, ...]]:
    """Count calls to known functions in the AST.

    Args:
        tree: Parsed AST module
        known_functions: Functions to count calls for
        position_index: Position-aware index for name resolution
        known_classes: Set of known class qualified names for __init__ resolution
        source_code: Source code for error context

    Returns:
        Tuple of (resolved call counts, unresolvable calls)
    """
    visitor = CallCountVisitor(known_functions, position_index, known_classes, source_code)
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

    Usage:
        After calling visit() on an AST tree, access the 'call_counts' dictionary
        to retrieve the updated call counts for each function:

        >>> visitor = CallCountVisitor(known_functions, position_index, known_classes, source_code)
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
        position_index: PositionIndex,
        known_classes: set[QualifiedName],
        source_code: str,
    ) -> None:
        """Initialize visitor with functions to track and position index.

        Args:
            known_functions: Functions to count calls for
            position_index: Position-aware index for name resolution
            known_classes: Set of known class qualified names for __init__ resolution
            source_code: Source code for extracting unresolvable call text
        """
        super().__init__()
        # Create internal call count tracking from known functions
        self.call_counts: dict[QualifiedName, int] = {func.qualified_name: 0 for func in known_functions}
        self._position_index = position_index
        self._known_classes = known_classes
        self._scope_stack = create_initial_stack()
        self._source_code = source_code
        self._unresolvable_calls: list[UnresolvableCall] = []

    def _resolve_name_at_position(self, name: str, lineno: int) -> NameBinding | None:
        """Resolve a name at a specific position using the current scope context.

        Args:
            name: The name to resolve
            lineno: Line number for position-aware resolution

        Returns:
            NameBinding if the name can be resolved, None otherwise
        """
        return resolve_name(
            self._position_index,
            name,
            lineno,
            self._scope_stack,
            get_execution_context(self._scope_stack),
        )

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class definition, tracking it as a scope.

        Class bodies execute IMMEDIATELY when the class is defined, even if
        the class definition is nested inside a function.
        """
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit a function definition, tracking it as a scope.

        Function bodies execute DEFERRED - only when the function is called,
        not when it's defined. This allows forward references.
        """
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit an async function definition, tracking it as a scope.

        Async function bodies also execute DEFERRED.
        """
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        """Visit function call to count calls to known functions."""
        call_name = self._resolve_call_name(node)

        match call_name:
            case name if name and name in self.call_counts:
                # Resolved and in known_functions - increment count
                self.call_counts[name] += 1
            case None if not _is_builtin_call(node):
                # Unresolvable and not a builtin - track for diagnostics
                self._track_unresolvable_call(node)
            case _:
                # Resolved but not in known_functions, or builtin - ignore
                pass

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

        Handles both function calls and class instantiations. When a name
        refers to a known class, resolves to ClassName.__init__.

        Returns:
            Qualified function name if resolvable, None otherwise.
        """
        func = node.func

        if isinstance(func, ast.Name):
            return self._resolve_direct_call(func)

        if isinstance(func, ast.Attribute):
            resolved = self._resolve_method_call(func)
            if resolved and resolved in self._known_classes:
                # It's actually a nested class instantiation like Outer.Inner()
                return make_qualified_name(f"{resolved}.__init__")
            return resolved

        # Dynamic calls: getattr(obj, 'method')(), obj[key](), etc.
        # Cannot be resolved statically
        return None

    def _resolve_direct_call(self, func: ast.Name) -> QualifiedName | None:
        """Resolve direct function calls and class instantiations using position-aware index.

        Handles calls like function_name() or ClassName(), where the latter
        is resolved to ClassName.__init__.

        Args:
            func: The ast.Name node representing the called name

        Returns:
            Qualified name if resolvable, None otherwise
        """
        binding = self._resolve_name_at_position(func.id, func.lineno)

        if binding is None or binding.kind == NameBindingKind.IMPORT:
            # Unresolvable or imported (Phase 1 limitation)
            return None

        if binding.kind == NameBindingKind.CLASS:
            # Class instantiation - resolve to __init__
            return make_qualified_name(f"{binding.qualified_name}.__init__")

        if binding.kind == NameBindingKind.FUNCTION:
            # Regular function call
            return binding.qualified_name

        # Variables aren't directly callable
        return None

    def _resolve_self_or_cls_method_call(self, func: ast.Attribute) -> QualifiedName | None:
        """Resolve self.method() or cls.method() calls to their qualified names.

        Args:
            func: The ast.Attribute node representing the method call

        Returns:
            Qualified method name if this is a self/cls method call, None otherwise
        """
        if not isinstance(func.value, ast.Name) or func.value.id not in ("self", "cls"):
            return None

        class_qualified = get_containing_class_qualified_name(self._scope_stack)
        if class_qualified:
            return make_qualified_name(f"{class_qualified}.{func.attr}")
        return None

    def _resolve_single_name_method_call(self, func: ast.Attribute) -> QualifiedName | None:
        """Resolve variable.method() or ClassName.method() calls.

        Args:
            func: The ast.Attribute node representing the method call

        Returns:
            Qualified method name if resolvable, None otherwise
        """
        if not isinstance(func.value, ast.Name):
            return None

        binding = self._resolve_name_at_position(func.value.id, func.lineno)

        if binding and binding.kind == NameBindingKind.VARIABLE and binding.target_class:
            # We know what class the variable refers to
            return make_qualified_name(f"{binding.target_class}.{func.attr}")

        # Check if it's a class reference for ClassName.method() calls
        if binding and binding.kind == NameBindingKind.CLASS:
            return make_qualified_name(f"{binding.qualified_name}.{func.attr}")

        return None

    def _resolve_compound_method_call(self, func: ast.Attribute) -> QualifiedName | None:
        """Resolve compound method calls like Outer.Inner.method().

        Args:
            func: The ast.Attribute node representing the method call

        Returns:
            Qualified method name if resolvable, None otherwise
        """
        if not isinstance(func.value, ast.Attribute):
            return None

        # Try to resolve the compound class reference
        resolved_class = self._resolve_compound_class_reference(func.value, func.lineno)
        if resolved_class:
            return make_qualified_name(f"{resolved_class}.{func.attr}")

        return None

    def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
        """Resolve qualified name from a method call using position-aware index.

        Handles self.method(), cls.method(), ClassName.method(), variable.method(),
        and compound class references like Outer.Inner.method() calls.

        Args:
            func: The ast.Attribute node representing the method call

        Returns:
            Qualified method name if resolvable, None otherwise
        """
        # Try each resolution strategy in order
        return (
            self._resolve_self_or_cls_method_call(func)
            or self._resolve_single_name_method_call(func)
            or self._resolve_compound_method_call(func)
        )

    def _resolve_compound_class_reference(self, node: ast.Attribute, lineno: int) -> QualifiedName | None:
        """Resolve a compound class reference like Outer.Inner or obj.Inner.

        Handles both direct class references (Outer.Inner) and references through
        instance variables (obj.Inner where obj is an instance of Outer).

        Args:
            node: The ast.Attribute node representing the compound reference
            lineno: Line number for position-aware resolution

        Returns:
            Qualified name of the class if resolvable, None otherwise
        """
        # Extract attribute chain (e.g., ['Outer', 'Inner'])
        parts = _extract_attribute_chain(node)
        if not parts:
            return None

        # Resolve the leftmost name
        binding = self._resolve_name_at_position(parts[0], lineno)
        if not binding:
            return None

        # Get base qualified name from either CLASS or VARIABLE with target_class
        if binding.kind == NameBindingKind.CLASS:
            base_qualified = binding.qualified_name
        elif binding.kind == NameBindingKind.VARIABLE and binding.target_class is not None:
            base_qualified = binding.target_class
        else:
            return None

        # Build the full qualified name by appending the rest of the parts
        full_qualified = make_qualified_name(f"{base_qualified}.{'.'.join(parts[1:])}")

        # Verify this class actually exists in known_classes
        if full_qualified in self._known_classes:
            return full_qualified

        return None
