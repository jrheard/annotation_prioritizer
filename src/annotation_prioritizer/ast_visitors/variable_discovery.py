"""AST visitor for discovering variable-to-type mappings."""

import ast
import logging
from typing import override

from annotation_prioritizer.ast_arguments import iter_all_arguments
from annotation_prioritizer.ast_visitors.class_discovery import ClassRegistry
from annotation_prioritizer.models import QualifiedName, Scope, ScopeKind
from annotation_prioritizer.scope_tracker import (
    add_scope,
    create_initial_stack,
    drop_last_scope,
    resolve_name_in_scope,
)
from annotation_prioritizer.variable_registry import VariableRegistry, VariableType

logger = logging.getLogger(__name__)


class VariableDiscoveryVisitor(ast.NodeVisitor):
    """AST visitor that builds a registry of variable-to-type mappings.

    Part of Stage 1 (discovery stage) of the two-stage analysis. Discovers variables through:
    1. Direct instantiation: calc = Calculator()
    2. Parameter annotations: def foo(calc: Calculator)
    3. Variable annotations: calc: Calculator = ...

    Handles reassignment by tracking the most recent type.

    Usage:
        visitor = VariableDiscoveryVisitor(class_registry)
        visitor.visit(tree)
        registry = visitor.get_registry()
    """

    def __init__(self, class_registry: ClassRegistry) -> None:
        """Initialize tracker with known classes.

        Args:
            class_registry: Registry of known classes for type validation
        """
        super().__init__()
        self._class_registry = class_registry
        self._scope_stack = create_initial_stack()
        self._variables: dict[QualifiedName, VariableType] = {}

    def get_registry(self) -> VariableRegistry:
        """Return the built variable registry as an immutable registry."""
        return VariableRegistry(variables=self._variables)

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class scope."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function scope and parameter annotations."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))

        # Process all parameter annotations (including kwargs, *args, etc.)
        for arg, _ in iter_all_arguments(node.args):
            if arg.annotation:
                self._process_annotation(arg.arg, arg.annotation)

        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function scope and parameter annotations."""
        self.visit_FunctionDef(node)  # pyright: ignore[reportArgumentType]

    @override
    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Handle annotated assignments like calc: Calculator = ..."""
        if isinstance(node.target, ast.Name):
            self._process_annotation(node.target.id, node.annotation)
        else:
            # Log when we skip complex annotated assignments
            logger.debug(
                "Cannot track annotated assignment: complex target type %s not supported",
                type(node.target).__name__,
            )
        self.generic_visit(node)

    @override
    def visit_Assign(self, node: ast.Assign) -> None:
        """Handle assignments like calc = Calculator()."""
        # Only handle simple assignments to single names
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            variable_name = node.targets[0].id

            # Check if it's a direct instantiation
            if isinstance(node.value, ast.Call):
                class_name = self._extract_class_from_call(node.value)
                if class_name:
                    self._track_variable(variable_name, class_name, is_instance=True)
                else:
                    # Log when we can't resolve a call to a known class
                    logger.debug(
                        "Cannot track assignment to '%s': call is not to a known class constructor",
                        variable_name,
                    )
            # Check if it's a class reference (calc = Calculator)
            elif isinstance(node.value, ast.Name):
                if self._resolve_class_name(node.value.id):
                    self._track_variable(variable_name, node.value.id, is_instance=False)
                else:
                    # Log when we encounter a name that isn't a known class
                    logger.debug(
                        "Cannot track assignment to '%s': '%s' is not a known class",
                        variable_name,
                        node.value.id,
                    )
            else:
                # Log other assignment types we don't handle
                logger.debug(
                    "Cannot track assignment to '%s': unsupported value type %s",
                    variable_name,
                    type(node.value).__name__,
                )
        # Log when we skip complex assignments
        elif len(node.targets) > 1:
            logger.debug("Cannot track assignment: multiple targets not supported")
        elif node.targets and not isinstance(node.targets[0], ast.Name):
            logger.debug(
                "Cannot track assignment: complex target type %s not supported",
                type(node.targets[0]).__name__,
            )

        self.generic_visit(node)

    def _process_annotation(self, variable_name: str, annotation: ast.expr) -> None:
        """Process a type annotation."""
        if isinstance(annotation, ast.Name):
            class_name = annotation.id
            if self._resolve_class_name(class_name):
                self._track_variable(variable_name, class_name, is_instance=True)
            else:
                logger.debug(
                    "Cannot track annotation for '%s': '%s' is not a known class",
                    variable_name,
                    class_name,
                )
        else:
            # Log when we encounter complex annotations we don't handle
            logger.debug(
                "Cannot track annotation for '%s': complex annotation type %s not supported",
                variable_name,
                type(annotation).__name__,
            )
        # Could extend to handle Optional, Union, etc. in the future

    def _extract_class_from_call(self, call_node: ast.Call) -> str | None:
        """Extract class name from a call node if it's a known class constructor."""
        if isinstance(call_node.func, ast.Name):
            class_name = call_node.func.id
            if self._resolve_class_name(class_name):
                return class_name
        # Could handle Outer.Inner() in the future
        return None

    def _track_variable(self, variable_name: str, class_name: str, *, is_instance: bool) -> None:
        """Add or update a variable in the registry."""
        # Build key using the same format as generate_name_candidates
        parts = [scope.name for scope in self._scope_stack]
        key = QualifiedName(".".join([*parts, variable_name]))
        # Resolve class name to qualified form
        qualified_class = self._resolve_class_name(class_name)
        if qualified_class:
            variable_type = VariableType(class_name=qualified_class, is_instance=is_instance)
            self._variables[key] = variable_type

    def _resolve_class_name(self, class_name: str) -> QualifiedName | None:
        """Resolve a class name to its qualified form."""
        return resolve_name_in_scope(self._scope_stack, class_name, self._class_registry.classes)


def build_variable_registry(tree: ast.AST, class_registry: ClassRegistry) -> VariableRegistry:
    """Build a registry of variable-to-type mappings from an AST.

    This is the entry point for variable discovery (part of Stage 1).

    Args:
        tree: Parsed AST of the Python source
        class_registry: Known classes for type validation

    Returns:
        Registry mapping scope-qualified variable names to their types
    """
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    return visitor.get_registry()
