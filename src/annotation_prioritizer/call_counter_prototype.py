"""Prototype CallCountVisitor using position-aware resolution.

This is a simplified version of CallCountVisitor that uses PositionIndex
for position-aware name resolution to fix the shadowing bug.
"""

import ast
from typing import override

from annotation_prioritizer.models import (
    FunctionInfo,
    NameBindingKind,
    QualifiedName,
    Scope,
    ScopeKind,
    UnresolvableCall,
    make_qualified_name,
)
from annotation_prioritizer.position_index import PositionIndex
from annotation_prioritizer.scope_tracker import (
    ScopeStack,
    add_scope,
    create_initial_stack,
    drop_last_scope,
    extract_attribute_chain,
)


class CallCountVisitorPrototype(ast.NodeVisitor):
    """Prototype visitor using position-aware resolution."""

    def __init__(
        self,
        known_functions: tuple[FunctionInfo, ...],
        position_index: PositionIndex,
        source_code: str,
    ) -> None:
        """Initialize the prototype visitor."""
        super().__init__()
        self.call_counts: dict[QualifiedName, int] = {func.qualified_name: 0 for func in known_functions}
        self._position_index = position_index
        self._scope_stack: ScopeStack = create_initial_stack()
        self._source_code = source_code
        self._unresolvable_calls: list[UnresolvableCall] = []
        # Track which qualified names are classes for __init__ resolution
        self._known_classes: set[QualifiedName] = set()

    def set_known_classes(self, classes: set[QualifiedName]) -> None:
        """Set the known classes for __init__ resolution."""
        self._known_classes = classes

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition to track scope context."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition to track scope context."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition to track scope context."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        """Visit a function call node."""
        resolved = self._resolve_call(node)
        if resolved and resolved in self.call_counts:
            self.call_counts[resolved] += 1
        elif resolved is None:
            # Track unresolvable call
            line_number = node.lineno
            # Extract call text from source
            lines = self._source_code.splitlines()
            if 0 <= line_number - 1 < len(lines):
                call_text = lines[line_number - 1].strip()
            else:
                call_text = "<unavailable>"
            self._unresolvable_calls.append(UnresolvableCall(line_number=line_number, call_text=call_text))
        self.generic_visit(node)

    def _resolve_call(self, node: ast.Call) -> QualifiedName | None:
        """Resolve a call node to a qualified name using position-aware resolution."""
        func = node.func

        if isinstance(func, ast.Name):
            return self._resolve_direct_call(func)

        if isinstance(func, ast.Attribute):
            return self._resolve_method_call(func)

        # Dynamic calls cannot be resolved
        return None

    def _resolve_direct_call(self, func: ast.Name) -> QualifiedName | None:
        """Resolve direct function calls using position-aware index."""
        # Use position-aware resolution
        binding = self._position_index.resolve(func.id, func.lineno, self._scope_stack)

        if binding is None:
            return None

        # If it's an import, it's unresolvable in Phase 1
        if binding.kind == NameBindingKind.IMPORT:
            return None

        # If it's a class, resolve to __init__
        if binding.kind == NameBindingKind.CLASS and binding.qualified_name:
            return make_qualified_name(f"{binding.qualified_name}.__init__")

        # It's a function
        return binding.qualified_name

    def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
        """Resolve method calls like self.method() or ClassName.method()."""
        # Handle self.method() calls
        if isinstance(func.value, ast.Name) and func.value.id == "self":
            # Find the containing class
            for scope in reversed(self._scope_stack):
                if scope.kind == ScopeKind.CLASS:
                    # Build the method's qualified name
                    class_scopes = []
                    for s in self._scope_stack:
                        if s.kind != ScopeKind.FUNCTION:
                            class_scopes.append(s)
                        if s == scope:
                            break

                    # Build class qualified name
                    if class_scopes:
                        parts = [s.name for s in class_scopes]
                        class_qualified = make_qualified_name(".".join(parts))
                        return make_qualified_name(f"{class_qualified}.{func.attr}")
            return None

        # Handle variable.method() calls
        if isinstance(func.value, ast.Name):
            # Look up the variable
            binding = self._position_index.resolve(
                func.value.id,
                func.lineno,
                self._scope_stack
            )

            if binding and binding.kind == NameBindingKind.VARIABLE and binding.target_class:
                # We know what class the variable refers to
                return make_qualified_name(f"{binding.target_class}.{func.attr}")

        # Handle ClassName.method() - extract the full attribute chain
        try:
            # Get the full chain including the final attribute
            full_chain = extract_attribute_chain(func)
            if full_chain and len(full_chain) >= 2:
                # The first element is the base name to resolve
                base_name = full_chain[0]

                # Try to resolve the base name
                binding = self._position_index.resolve(base_name, func.lineno, self._scope_stack)

                if binding and binding.kind == NameBindingKind.CLASS and binding.qualified_name:
                    # Build the full qualified name
                    # Replace the base with the qualified name and keep the rest of the chain
                    parts = [str(binding.qualified_name)] + list(full_chain[1:])
                    full_name = ".".join(parts)

                    result = make_qualified_name(full_name)

                    # Check if this is actually a nested class instantiation
                    # (the last element before the final attribute is a class)
                    if len(full_chain) >= 3:
                        # Check if the second-to-last element might be a class
                        potential_class = ".".join(parts[:-1])
                        potential_class_qn = make_qualified_name(potential_class)
                        if potential_class_qn in self._known_classes:
                            return make_qualified_name(f"{potential_class_qn}.__init__")

                    return result
        except (AssertionError, AttributeError):
            # extract_attribute_chain can throw for complex expressions
            pass

        return None
